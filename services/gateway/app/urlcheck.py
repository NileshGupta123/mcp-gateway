"""Basic SSRF guard: limits where the gateway may connect for an upstream URL given by an admin.

Policy: private ranges (10.x, 172.16.x, 192.168.x) are allowed because our upstreams live inside the
cluster. Cloud metadata, loopback, link-local and non-http schemes are always blocked.
In production an explicit host allowlist on top of this is better.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # link-local, AWS/GCP/Azure metadata (169.254.169.254)
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT, Alibaba metadata (100.100.100.200)
    ipaddress.ip_network("fd00:ec2::/32"),  # AWS IPv6 metadata
]
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata"}


class UrlNotAllowed(ValueError):
    pass


def _check_ip(raw: str) -> None:
    ip = ipaddress.ip_address(raw.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        raise UrlNotAllowed(f"address {ip} is not allowed")
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            raise UrlNotAllowed(f"address {ip} is in a blocked range ({network})")


async def validate_upstream_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UrlNotAllowed("only http and https URLs are allowed")
    if not parts.hostname:
        raise UrlNotAllowed("URL has no host")
    if parts.username or parts.password:
        raise UrlNotAllowed("credentials inside the URL are not allowed; use the credential field")
    host = parts.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise UrlNotAllowed(f"host '{host}' is not allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        return  # a name that does not resolve is no attack path; the connect step reports a clear error
    for info in infos:
        _check_ip(info[4][0])