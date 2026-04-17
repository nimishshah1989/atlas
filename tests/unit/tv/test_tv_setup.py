"""V6T-1: Verify tradingview-screener pin and config setup."""

import importlib


def test_tradingview_screener_importable() -> None:
    """tradingview-screener==3.1.0 must be importable."""
    mod = importlib.import_module("tradingview_screener")
    assert mod is not None


def test_config_has_tv_webhook_secret() -> None:
    """Settings must expose tv_webhook_secret."""
    from backend.config import Settings

    s = Settings()
    assert hasattr(s, "tv_webhook_secret")
    assert isinstance(s.tv_webhook_secret, str)


def test_config_has_tv_cache_ttl_seconds() -> None:
    """Settings must expose tv_cache_ttl_seconds."""
    from backend.config import Settings

    s = Settings()
    assert hasattr(s, "tv_cache_ttl_seconds")
    assert isinstance(s.tv_cache_ttl_seconds, int)
    assert s.tv_cache_ttl_seconds > 0


def test_config_no_tv_bridge_url() -> None:
    """tv_bridge_url must NOT be in Settings (dead config removed)."""
    from backend.config import Settings

    s = Settings()
    assert not hasattr(s, "tv_bridge_url")
