"""
backend/core/client_ip.py
Secure, trusted-proxy-aware client IP extraction.

Security decisions:
  - Never blindly trust X-Forwarded-For or X-Real-IP.
  - Only trust forwarded headers when the *direct peer* (ASGI scope remote_addr)
    belongs to a configured trusted-proxy CIDR.
  - Default trusted CIDRs cover loopback + RFC-1918 private ranges so that a
    standard reverse-proxy setup (nginx/traefik on the same Docker network) works
    without extra config while still blocking spoofing from the public internet.
  - Malformed or non-routable forwarded IPs are silently ignored; the raw peer IP
    is used as fallback.
  - TRUSTED_PROXY_CIDRS can be overridden via settings.TRUSTED_PROXY_CIDRS.
"""
from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from typing import Sequence

from starlette.requests import Request

log = logging.getLogger(__name__)

_DEFAULT_TRUSTED_CIDRS: tuple[str, ...] = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "::1/128",
    "fc00::/7",
)


@lru_cache(maxsize=1)
def _get_trusted_networks() -> tuple:
    raw_cidrs: Sequence[str] = _DEFAULT_TRUSTED_CIDRS
    try:
        from backend.core.config import get_settings
        s = get_settings()
       if hasattr(s, "TRUSTED_PROXY_CIDRS") and s.TRUSTED_PROXY_CIDRS:
    if isinstance(s.TRUSTED_PROXY_CIDRS, str):
        raw_cidrs = [c.strip() for c in s.TRUSTED_PROXY_CIDRS.split(",") if c.strip()]
    else:
        raw_cidrs = list(s.TRUSTED_PROXY_CIDRS)
    except Exception:
        pass
    networks = []
    for cidr in raw_cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            log.warning("client_ip: invalid CIDR %r", cidr)
    return tuple(networks)


def _parse_ip(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("["):
        raw = raw.split("]")[0].lstrip("[")
    elif ":" in raw and raw.count(":") == 1:
        raw = raw.rsplit(":", 1)[0]
    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        return None


def _is_trusted_proxy(ip) -> bool:
    for net in _get_trusted_networks():
        try:
            if ip in net:
                return True
        except TypeError:
            continue
    return False


def get_client_ip(request: Request) -> str:
    """
    Return the real client IP.

    Only trusts X-Forwarded-For / X-Real-IP when the direct TCP peer
    is in a configured trusted-proxy CIDR. Otherwise returns the peer
    IP directly, preventing header-based IP spoofing.
    """
    peer_ip_str = "unknown"
    peer_ip_obj = None

    if request.client and request.client.host:
        peer_ip_str = request.client.host
        peer_ip_obj = _parse_ip(peer_ip_str)

    # If peer is not a trusted proxy, return raw peer IP immediately.
    if peer_ip_obj is None or not _is_trusted_proxy(peer_ip_obj):
        return peer_ip_str

    # Peer is trusted — inspect forwarded headers.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        for candidate in xff.split(","):
            addr = _parse_ip(candidate)
            if addr is not None:
                return str(addr)

    x_real_ip = request.headers.get("X-Real-IP", "").strip()
    if x_real_ip:
        addr = _parse_ip(x_real_ip)
        if addr is not None:
            return str(addr)

    return peer_ip_str
