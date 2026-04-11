"""Проверки URL для исходящих HTTP-запросов (снижение риска SSRF)."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google.internal.",
    },
)


def is_safe_outbound_webhook_url(url: str, *, allow_private: bool) -> bool:
    """Проверка URL для исходящего webhook.

    При ``allow_private=False`` блокируются небезопасные литеральные хосты и
    IP из частных, loopback и link-local диапазонов. Доменное имя, которое
    резолвится в частный адрес, отдельно не проверяется — используйте доверенные
    URL в конфигурации или включайте ``OUTBOUND_WEBHOOK_ALLOW_PRIVATE_IPS`` только
    в изолированной сети.
    """
    if allow_private:
        return True
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    lowered = host.lower().rstrip(".")
    if lowered in _BLOCKED_HOSTS or lowered == "169.254.169.254":
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )
