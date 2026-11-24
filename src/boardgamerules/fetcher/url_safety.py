"""Asynchronous SSRF URL and IP address validation for external rulebook downloads."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import SplitResult, urlsplit

from boardgamerules.domain.exceptions import ExternalRuleFetchError

type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type HostResolver = Callable[[str, int], Awaitable[tuple[IpAddress, ...]]]

_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal")


# CONCEPT: [System Design] SSRF Protection (Blocking Private Networks & Cloud Metadata)
# When a server downloads URLs discovered on the internet, an attacker could supply a link
# pointing to localhost (127.0.0.1) or GCP's internal metadata server (169.254.169.254) to
# steal cloud credentials. Before every download and every redirect hop, we check the scheme,
# port, and resolved IP addresses to make sure we only connect to public internet servers.
async def validate_safe_public_url(
    url: str,
    *,
    resolve_host: HostResolver | None = None,
) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ExternalRuleFetchError("Candidate rulebook URL cannot be empty.")

    parsed = _parse_url_safely(cleaned)
    _validate_https_scheme(parsed.scheme)
    _validate_authority(parsed)
    port = _resolve_https_port(parsed)
    hostname = _require_public_hostname(parsed.hostname)

    literal_ip = _try_parse_ip_literal(hostname)
    if literal_ip is not None:
        ips: tuple[IpAddress, ...] = (literal_ip,)
    else:
        resolver = resolve_host or _resolve_host_ips
        ips = await resolver(hostname, port)
    if not ips:
        raise ExternalRuleFetchError(f"Host '{hostname}' did not resolve to any IP address.")

    for ip in ips:
        _ensure_global_ip(ip, hostname)
    return cleaned


def _parse_url_safely(url: str) -> SplitResult:
    try:
        return urlsplit(url)
    except ValueError as exc:
        raise ExternalRuleFetchError(f"Malformed candidate URL: {exc}") from exc


def _validate_https_scheme(scheme: str) -> None:
    if scheme.lower() != "https":
        raise ExternalRuleFetchError(f"Only HTTPS URLs are allowed, got '{scheme}'.")


def _validate_authority(parsed: SplitResult) -> None:
    if parsed.username is not None or parsed.password is not None:
        raise ExternalRuleFetchError("URLs containing embedded credentials are not allowed.")


def _resolve_https_port(parsed: SplitResult) -> int:
    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise ExternalRuleFetchError(f"Invalid port in candidate URL: {exc}") from exc

    resolved_port = 443 if explicit_port is None else explicit_port
    if resolved_port != 443:
        raise ExternalRuleFetchError(f"Non-standard port {resolved_port} is not allowed.")
    return resolved_port


def _require_public_hostname(hostname: str | None) -> str:
    if not hostname:
        raise ExternalRuleFetchError("Candidate URL is missing a hostname.")
    lowered = hostname.lower().rstrip(".")
    if lowered in _BLOCKED_HOSTNAMES or lowered.endswith(_BLOCKED_SUFFIXES):
        raise ExternalRuleFetchError(f"Blocked internal hostname '{hostname}'.")
    return lowered


async def _resolve_host_ips(hostname: str, port: int) -> tuple[IpAddress, ...]:
    loop = asyncio.get_running_loop()
    try:
        addr_infos = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ExternalRuleFetchError(f"DNS lookup failed for '{hostname}': {exc}") from exc

    return tuple(ipaddress.ip_address(info[4][0]) for info in addr_infos)


def _try_parse_ip_literal(hostname: str) -> IpAddress | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


def _ensure_global_ip(ip: IpAddress, hostname: str) -> None:
    effective_ip: IpAddress = ip
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        effective_ip = ip.ipv4_mapped
    if not effective_ip.is_global or effective_ip.is_multicast:
        raise ExternalRuleFetchError(
            f"Refusing to connect to non-public IP resolved for '{hostname}'."
        )
