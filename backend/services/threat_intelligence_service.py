from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger(__name__)

ENABLED: bool = os.getenv("THREAT_INTEL_ENABLED", "false").lower() in ("1", "true", "yes")
PROVIDER: str = os.getenv("THREAT_INTEL_PROVIDER", "abuseipdb").lower()
API_KEY: str = os.getenv("THREAT_INTEL_API_KEY", "")
CACHE_TTL: int = int(os.getenv("THREAT_INTEL_CACHE_TTL", "3600"))
TIMEOUT: float = float(os.getenv("THREAT_INTEL_TIMEOUT", "5.0"))

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return True


class ThreatLevel(str, Enum):
    CLEAN = "clean"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatReport:
    ip: str
    threat_level: ThreatLevel = ThreatLevel.CLEAN
    confidence_score: float = 0.0
    abuse_score: int = 0
    is_tor: bool = False
    is_vpn: bool = False
    is_datacenter: bool = False
    country_code: str = ""
    reports_count: int = 0
    last_reported_at: Optional[str] = None
    provider: str = "local"
    cached: bool = False
    error: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def risk_score(self) -> float:
        base = self.confidence_score / 100.0
        if self.is_tor:
            base = min(1.0, base + 0.3)
        if self.is_datacenter:
            base = min(1.0, base + 0.1)
        return round(base, 4)


class _Cache:
    def __init__(self, ttl: int) -> None:
        self._store: Dict[str, tuple] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._MAX = 50_000

    async def get(self, ip: str) -> Optional[ThreatReport]:
        async with self._lock:
            entry = self._store.get(ip)
            if entry and (time.monotonic() - entry[0]) < self._ttl:
                r = entry[1]
                r.cached = True
                return r
            if entry:
                del self._store[ip]
            return None

    async def set(self, ip: str, report: ThreatReport) -> None:
        async with self._lock:
            if len(self._store) >= self._MAX:
                evict_n = self._MAX // 10
                for k in list(self._store.keys())[:evict_n]:
                    del self._store[k]
            self._store[ip] = (time.monotonic(), report)


class _AbuseIPDBProvider:
    _URL = "https://api.abuseipdb.com/api/v2/check"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    async def check(self, ip: str, client: httpx.AsyncClient) -> ThreatReport:
        r = ThreatReport(ip=ip, provider="abuseipdb")
        try:
            resp = await client.get(
                self._URL,
                headers={"Key": self._key, "Accept": "application/json"},
                params={"ipAddress": ip, "maxAgeInDays": "90"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            score: int = data.get("abuseConfidenceScore", 0)
            r.abuse_score = score
            r.confidence_score = float(score)
            r.country_code = data.get("countryCode", "")
            r.reports_count = data.get("totalReports", 0)
            r.last_reported_at = data.get("lastReportedAt")
            r.is_tor = bool(data.get("isTor", False))
            r.raw = data
            r.threat_level = _score_to_level(score)
        except Exception as exc:
            r.error = f"abuseipdb: {type(exc).__name__}"
            log.debug("AbuseIPDB error for %s: %s", ip, exc)
        return r


class _VirusTotalProvider:
    _URL = "https://www.virustotal.com/api/v3/ip_addresses/{ip}"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    async def check(self, ip: str, client: httpx.AsyncClient) -> ThreatReport:
        r = ThreatReport(ip=ip, provider="virustotal")
        try:
            resp = await client.get(
                self._URL.format(ip=ip),
                headers={"x-apikey": self._key},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            attrs = resp.json().get("data", {}).get("attributes", {})
            stats: Dict[str, int] = attrs.get("last_analysis_stats", {})
            malicious: int = stats.get("malicious", 0)
            suspicious: int = stats.get("suspicious", 0)
            total: int = sum(stats.values()) or 1
            score = round(((malicious * 1.0 + suspicious * 0.5) / total) * 100, 1)
            r.confidence_score = score
            r.abuse_score = int(score)
            r.country_code = attrs.get("country", "")
            r.is_tor = "TOR" in str(attrs.get("tags", []))
            r.is_vpn = "VPN" in str(attrs.get("tags", []))
            r.raw = attrs
            r.threat_level = _score_to_level(score)
        except Exception as exc:
            r.error = f"virustotal: {type(exc).__name__}"
            log.debug("VirusTotal error for %s: %s", ip, exc)
        return r


class _CloudflareProvider:
    _URL = "https://api.cloudflare.com/client/v4/radar/entities/ip?ip={ip}"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    async def check(self, ip: str, client: httpx.AsyncClient) -> ThreatReport:
        r = ThreatReport(ip=ip, provider="cloudflare")
        try:
            resp = await client.get(
                self._URL.format(ip=ip),
                headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            ip_info = resp.json().get("result", {}).get("ipAddress", {})
            is_bot = bool(ip_info.get("botStatus") == "verified_bot")
            asn_type = str(ip_info.get("asnType", "")).lower()
            r.is_datacenter = "hosting" in asn_type or "datacenter" in asn_type
            r.country_code = str(ip_info.get("geoIpCountry", ""))
            score = 20.0 if is_bot else 0.0
            if r.is_datacenter:
                score += 10.0
            r.confidence_score = score
            r.threat_level = _score_to_level(score)
            r.raw = ip_info
        except Exception as exc:
            r.error = f"cloudflare: {type(exc).__name__}"
            log.debug("Cloudflare error for %s: %s", ip, exc)
        return r


class _LocalProvider:
    async def check(self, ip: str, _client: httpx.AsyncClient) -> ThreatReport:
        return ThreatReport(ip=ip, provider="local", threat_level=ThreatLevel.CLEAN)


def _score_to_level(score: float) -> ThreatLevel:
    if score >= 80:
        return ThreatLevel.CRITICAL
    if score >= 60:
        return ThreatLevel.HIGH
    if score >= 30:
        return ThreatLevel.MEDIUM
    if score >= 10:
        return ThreatLevel.LOW
    return ThreatLevel.CLEAN


class ThreatIntelligenceService:
    def __init__(self) -> None:
        self._enabled = ENABLED
        self._cache = _Cache(ttl=CACHE_TTL)
        self._client: Optional[httpx.AsyncClient] = None
        self._provider: Any = self._build_provider()
        self._lock = asyncio.Lock()
        self._stats = {"hits": 0, "misses": 0, "errors": 0, "local_only": 0}
        if self._enabled:
            log.info("ThreatIntel: enabled provider=%s", PROVIDER)
        else:
            log.info("ThreatIntel: disabled local-only mode")

    def _build_provider(self) -> Any:
        if not ENABLED or not API_KEY:
            return _LocalProvider()
        mapping = {
            "abuseipdb": _AbuseIPDBProvider,
            "virustotal": _VirusTotalProvider,
            "cloudflare": _CloudflareProvider,
        }
        cls = mapping.get(PROVIDER)
        if cls is None:
            log.warning("ThreatIntel: unknown provider %r falling back to local", PROVIDER)
            return _LocalProvider()
        return cls(API_KEY)

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(TIMEOUT),
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                    follow_redirects=False,
                )
            return self._client

    async def check_ip(self, ip: str) -> ThreatReport:
        if _is_private(ip):
            self._stats["local_only"] += 1
            return ThreatReport(ip=ip, provider="local", threat_level=ThreatLevel.CLEAN)
        cached = await self._cache.get(ip)
        if cached:
            self._stats["hits"] += 1
            return cached
        self._stats["misses"] += 1
        try:
            client = await self._get_client()
            report = await asyncio.wait_for(
                self._provider.check(ip, client), timeout=TIMEOUT + 1.0
            )
        except asyncio.TimeoutError:
            self._stats["errors"] += 1
            report = ThreatReport(ip=ip, provider="local", error="timeout")
        except Exception as exc:
            self._stats["errors"] += 1
            report = ThreatReport(ip=ip, provider="local", error=str(exc)[:120])
        await self._cache.set(ip, report)
        return report

    async def enrich_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        ip = str(event.get("ip", ""))
        if not ip:
            return event
        try:
            report = await self.check_ip(ip)
            event["threat_intel"] = {
                "threat_level": report.threat_level.value,
                "confidence_score": report.confidence_score,
                "is_tor": report.is_tor,
                "is_vpn": report.is_vpn,
                "is_datacenter": report.is_datacenter,
                "country_code": report.country_code,
                "provider": report.provider,
                "cached": report.cached,
                "risk_score": report.risk_score,
            }
        except Exception as exc:
            log.debug("ThreatIntel enrich error: %s", exc)
            event["threat_intel"] = {"error": "unavailable"}
        return event

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "provider": PROVIDER if self._enabled else "local",
            "cache_ttl_seconds": CACHE_TTL,
            **self._stats,
        }

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


threat_intelligence_service = ThreatIntelligenceService()
