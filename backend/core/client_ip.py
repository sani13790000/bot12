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
  - Malformed forwarded IPs are silently ignored; the raw peer IP
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
def _get_trusted_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    """
    Load trusted proxy CIDRs from settings.

    Supports both formats:
      TRUSTED_PROXY_CIDRS="10.0.0.0/8,172.16.0.0/12"
      TRUSTED_PROXY_CIDRS=["10.0.0.0/8", "172.16.0.0/12"]

    Falls back to _DEFAULT_TRUSTED_CIDRS if config is absent or invalid.
    """
    raw_cidrs: Sequence[str] = _DEFAULT_TRUSTED_CIDRS

    try:
        from backend.core.config import get_settings

        s = get_settings()
        trusted_proxy_cidrs = getattr(s, "TRUSTED_PROXY_CIDRS", None)

        if trusted_proxy_cidrs:
            if isinstance(trusted_proxy_cidrs, str):
                raw_cidrs = [
                    c.strip()
                    for c in trusted_proxy_cidrs.split(",")
                    if c.strip()
                ]
            else:
                raw_cidrs = [
                    str(c).strip()
                    for c in trusted_proxy_cidrs
                    if str(c).strip()
                ]

    except Exception as exc:
        log.debug("client_ip: failed to load TRUSTED_PROXY_CIDRS: %s", exc)

    networks: list[ipaddress._BaseNetwork] = []

    for cidr in raw_cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            log.warning("client_ip: invalid CIDR %r", cidr)

    return tuple(networks)


def _parse_ip(raw: str | None):
    """
    Parse IPv4/IPv6 addresses safely.

    Handles:
      - "1.2.3.4"
      - "1.2.3.4:12345"
      - "[2001:db8::1]:443"
      - "2001:db8::1"
    """
    if not raw:
        return None

    raw = raw.strip()

    if not raw:
        return None

    # IPv6 with brackets, e.g. [2001:db8::1]:443
    if raw.startswith("["):
        raw = raw.split("]", 1)[0].lstrip("[")

    # IPv4 with port, e.g. 192.168.1.10:12345
    elif ":" in raw and raw.count(":") == 1:
        host, port = raw.rsplit(":", 1)
        if port.isdigit():
            raw = host

    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        return None


def _is_trusted_proxy(ip: ipaddress._BaseAddress) -> bool:
    """
    Return True if direct peer IP belongs to configured trusted proxy networks.
    """
    for net in _get_trusted_networks():
        try:
            if ip in net:
                return True
        except TypeError:
            # IPv4 address compared to IPv6 network or vice versa.
            continue

    return False


def get_client_ip(request: Request) -> str:
    """
    Return the real client IP.

    Important:
      - X-Forwarded-For and X-Real-IP are trusted only if the direct TCP peer
        is a trusted proxy.
      - If the peer is not trusted, returns request.client.host directly.
      - This prevents header-based IP spoofing from public clients.
    """
    peer_ip_str = "unknown"
    peer_ip_obj = None

    if request.client and request.client.host:
        peer_ip_str = request.client.host
        peer_ip_obj = _parse_ip(peer_ip_str)

    # If peer is missing, malformed, or not a trusted proxy,
    # never trust forwarded headers.
    if peer_ip_obj is None or not _is_trusted_proxy(peer_ip_obj):
        return peer_ip_str

    # Peer is trusted — inspect X-Forwarded-For.
    #
    # Common format:
    #   X-Forwarded-For: client, proxy1, proxy2
    #
    # Since the direct peer is already trusted, the left-most valid address
    # is treated as the originating client.
    xff = request.headers.get("X-Forwarded-For", "")

    if xff:
        for candidate in xff.split(","):
            addr = _parse_ip(candidate)
            if addr is not None:
                return str(addr)

    # Fallback to X-Real-IP if XFF is absent or unusable.
    x_real_ip = request.headers.get("X-Real-IP", "")

    if x_real_ip:
        addr = _parse_ip(x_real_ip)
        if addr is not None:
            return str(addr)

    return peer_ip_str
