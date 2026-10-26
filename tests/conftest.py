"""Keep the test suite offline even when ~/.config/hackathon/secrets.env sets LIVE=1 and real keys."""
import pytest


@pytest.fixture(autouse=True)
def _offline_by_default(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    for name in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "RECORD_FIXTURES", "JUDGE_CODE", "LIVE_DAILY_CAP"):
        monkeypatch.delenv(name, raising=False)

    import httpx

    def _no_network(url, *args, **kwargs):
        raise AssertionError(f"test tried a real HTTP call to {url}; monkeypatch httpx.post")

    monkeypatch.setattr(httpx, "post", _no_network)
