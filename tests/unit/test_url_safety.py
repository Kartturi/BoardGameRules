"""Unit tests for SSRF URL and IP address safety validation."""

from __future__ import annotations

import ipaddress

import pytest

from boardgamerules.domain.exceptions import ExternalRuleFetchError
from boardgamerules.fetcher.url_safety import validate_safe_public_url

_PUBLIC_IP = (ipaddress.ip_address("93.184.216.34"),)
_PRIVATE_IP = (ipaddress.ip_address("10.0.0.5"),)
_METADATA_IP = (ipaddress.ip_address("169.254.169.254"),)
_IPV4_MAPPED_LOOPBACK = (ipaddress.ip_address("::ffff:127.0.0.1"),)


def _fake_resolver(
    ips: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...],
):
    async def _resolve(_host: str, _port: int):
        return ips

    return _resolve


@pytest.mark.anyio
async def test_should_allow_public_https_urls() -> None:
    # Arrange
    resolver = _fake_resolver(_PUBLIC_IP)

    # Act
    https_url = await validate_safe_public_url(
        "https://www.catan.com/sites/default/files/catan_rules.pdf",
        resolve_host=resolver,
    )

    # Assert
    assert https_url == "https://www.catan.com/sites/default/files/catan_rules.pdf"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "unsafe_url",
    [
        "file:///etc/passwd",
        "ftp://example.com/rules.pdf",
        "http://legacy.publisher.example/rules.pdf",
        "https://user:pass@example.com/rules.pdf",
        "https://example.com:8443/rules.pdf",
        "https://example.com:99999/rules.pdf",
        "https://example.com:abc/rules.pdf",
        "https://[::1/rules.pdf",
        "https://localhost/rules.pdf",
        "https://api.localhost/rules.pdf",
        "https://service.internal/rules.pdf",
        "https://127.0.0.1/rules.pdf",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::ffff:127.0.0.1]/rules.pdf",
        "",
    ],
)
async def test_should_reject_unsafe_schemes_ports_credentials_or_local_hosts(
    unsafe_url: str,
) -> None:
    # Arrange / Act / Assert
    with pytest.raises(ExternalRuleFetchError):
        await validate_safe_public_url(
            unsafe_url,
            resolve_host=_fake_resolver(_PUBLIC_IP),
        )


@pytest.mark.anyio
@pytest.mark.parametrize("resolved_ips", [_PRIVATE_IP, _METADATA_IP, _IPV4_MAPPED_LOOPBACK])
async def test_should_reject_hostname_resolving_to_non_global_ip(
    resolved_ips: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...],
) -> None:
    # Arrange / Act / Assert
    with pytest.raises(ExternalRuleFetchError):
        await validate_safe_public_url(
            "https://rebind.attacker.example/rules.pdf",
            resolve_host=_fake_resolver(resolved_ips),
        )
