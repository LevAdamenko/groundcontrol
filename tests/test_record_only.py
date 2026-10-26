"""Nemotron-only recording reuses Tavily fixtures without live search calls."""
import json
import os

import httpx
import pytest

from groundcontrol import clients, config
from groundcontrol.clients.tavily import TavilyClient
from scripts import record_fixtures


@pytest.mark.parametrize("previous", [None, "0", "1"])
def test_only_nemotron(monkeypatch, previous):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    if previous is not None:
        monkeypatch.setenv("RECORD_FIXTURES", previous)
    original_search = TavilyClient.search
    writes = []
    calls = []
    replays = []
    original_replay = TavilyClient._replay

    def replay(self, payload):
        replays.append(payload)
        return original_replay(self, payload)

    def post(url, **kwargs):
        assert "tavily.com" not in url
        assert url == config.get_nebius_base_url().rstrip("/") + "/chat/completions"
        calls.append(url)
        payload = kwargs["json"]
        if "response_format" in payload:
            # Existing extraction responses keep scenario facts and search queries exact.
            fixture = clients.get_fixtures_dir() / "nemotron" / (clients.stable_hash(payload) + ".json")
            response = json.loads(fixture.read_text())["response"]
            if isinstance(response, str):
                response = {"choices": [{"message": {"content": response}}]}
        else:
            response = {"choices": [{"message": {"content": "My flight was disrupted."}}]}
        return httpx.Response(200, json=response, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(TavilyClient, "_replay", replay)
    previous_hook = clients._RECORDER_HOOK
    clients.set_recorder_hook(lambda *args: writes.append(args))
    try:
        assert record_fixtures.main(["--only", "nemotron"]) == 0
    finally:
        clients.set_recorder_hook(previous_hook)
    assert calls and replays and writes
    assert len(writes) == len(calls)
    assert {write[0] for write in writes} == {"nemotron"}
    assert TavilyClient.search is original_search
    assert os.environ.get("RECORD_FIXTURES") == previous


def test_only_nemotron_dry_run(capsys):
    assert record_fixtures.main(["--dry-run", "--only", "nemotron"]) == 0
    output = capsys.readouterr().out
    assert "[Nemotron]" in output
    assert "[Tavily]" not in output


def test_only_nemotron_restores_after_failure(monkeypatch):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    original_search = TavilyClient.search

    def fail(sid):
        raise RuntimeError("scenario failed")

    monkeypatch.setattr(record_fixtures.pipeline, "run_scenario", fail)
    with pytest.raises(RuntimeError, match="scenario failed"):
        record_fixtures.main(["--only", "nemotron"])
    assert TavilyClient.search is original_search
    assert "RECORD_FIXTURES" not in os.environ
