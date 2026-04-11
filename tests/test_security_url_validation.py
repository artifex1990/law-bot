"""Тесты проверок URL для исходящего webhook (SSRF)."""

from src.security.url_validation import is_safe_outbound_webhook_url


def test_blocks_loopback_and_metadata_when_not_allowed():
    assert not is_safe_outbound_webhook_url(
        "http://127.0.0.1/webhook",
        allow_private=False,
    )
    assert not is_safe_outbound_webhook_url(
        "http://[::1]/webhook",
        allow_private=False,
    )
    assert not is_safe_outbound_webhook_url(
        "http://169.254.169.254/latest/meta-data/",
        allow_private=False,
    )
    assert not is_safe_outbound_webhook_url(
        "http://localhost/x",
        allow_private=False,
    )


def test_allow_private_overrides():
    assert is_safe_outbound_webhook_url(
        "http://127.0.0.1/webhook",
        allow_private=True,
    )


def test_allows_public_https():
    assert is_safe_outbound_webhook_url(
        "https://hooks.example.com/path",
        allow_private=False,
    )


def test_rejects_non_http():
    assert not is_safe_outbound_webhook_url(
        "ftp://example.com/x",
        allow_private=False,
    )
