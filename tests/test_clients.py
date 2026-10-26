"""Tests for client replay logic, stable hashing, and LIVE mode error handling."""
import pytest
from groundcontrol import config
from groundcontrol.clients import FixtureMissing, stable_hash
from groundcontrol.clients.nemotron import NemotronClient
from groundcontrol.clients.tavily import TavilyClient
from groundcontrol.verify import ALLOWED_DOMAINS


def test_stable_hash_deterministic():
    p1 = {"b": 2, "a": 1}
    p2 = {"a": 1, "b": 2}
    assert stable_hash(p1) == stable_hash(p2)
    assert len(stable_hash(p1)) == 16


def test_hash_excludes_api_key():
    client = TavilyClient(api_key="secret-tavily-key-12345")
    payload = client._build_payload("test query", include_domains=["europa.eu"])
    assert "api_key" not in payload
    assert "secret" not in str(payload)

    nemotron = NemotronClient()
    n_payload = nemotron._build_payload([{"role": "user", "content": "hi"}])
    assert "api_key" not in n_payload


def test_tavily_replay_works(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    client = TavilyClient()
    results = client.search("Regulation 261 2004 EUR 250 Article 7", include_domains=list(ALLOWED_DOMAINS))
    assert len(results) > 0
    assert any("EUR 250" in r.get("content", "") for r in results)


def test_nemotron_replay_works(monkeypatch):
    import json
    from groundcontrol.clients import get_fixtures_dir

    monkeypatch.setenv("LIVE", "0")
    recorded = [json.loads(p.read_text()) for p in sorted((get_fixtures_dir() / "nemotron").glob("*.json"))]
    fixture = next(f for f in recorded if f["recorded"] and "VQ202" in f["request"]["messages"][-1]["content"] and "response_format" not in f["request"])
    resp = NemotronClient().chat(fixture["request"]["messages"])
    assert resp == fixture["response"]["choices"][0]["message"]["content"]
    assert "VQ202" in resp


def test_live_mode_without_key_raises_nemotron(monkeypatch):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    client = NemotronClient()
    with pytest.raises(ValueError, match="NEBIUS_API_KEY"):
        client.chat([{"role": "user", "content": "hello"}])


def test_live_mode_without_key_raises_tavily(monkeypatch):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    client = TavilyClient()
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        client.search("Regulation 261")


def test_missing_fixture_raises_fixture_missing(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    client = TavilyClient()
    with pytest.raises(FixtureMissing) as exc_info:
        client.search("unrecorded query 123456789")
    assert "Tavily fixture missing" in str(exc_info.value)


def test_live_tavily_uses_basic_depth(monkeypatch):
    import httpx

    sent = {}

    def post(url, *args, **kwargs):
        sent.update(kwargs["json"])
        return httpx.Response(200, json={"results": []}, request=httpx.Request("POST", url))

    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", post)
    assert TavilyClient().search("Regulation 261") == []
    assert sent["search_depth"] == "basic"
