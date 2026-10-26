"""In-process judge access, persistence, replay isolation, and cost checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib
import json

from fastapi.testclient import TestClient
import pytest

from groundcontrol import live_access
from groundcontrol.demo import SCENARIO_IDS
from groundcontrol.web import app


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JUDGE_CODE", "private-judge-code")
    monkeypatch.setenv("NEBIUS_API_KEY", "private-nebius-key")
    monkeypatch.setenv("TAVILY_API_KEY", "private-tavily-key")
    with TestClient(app) as client:
        yield client


def unlock(client, **kwargs):
    return client.post("/api/unlock", json={"code": "private-judge-code"}, **kwargs)


def test_locked_and_wrong_code(hosted):
    for path in ("/api/run", "/api/live/run"):
        response = hosted.post(path, json={"text": "Own disruption"})
        assert response.status_code == 401
        assert response.json() == {"error": "live_locked"}
    for body in ({}, {"code": "wrong"}, {"code": None}, {"code": 123}, {"code": "🔑"}):
        response = hosted.post("/api/unlock", json=body)
        assert response.status_code == 401
        assert response.json() == {"error": "live_locked"}
    hosted.cookies.set("live_session", "forged")
    assert hosted.post("/api/live/run", json={"text": "own"}).status_code == 401


def test_rate_limit_last_forwarded_ip(hosted):
    headers = {"X-Forwarded-For": "192.0.2.1, 192.0.2.2"}
    for _ in range(10):
        assert hosted.post("/api/unlock", json={"code": "wrong"}, headers=headers).status_code == 401
    assert hosted.post("/api/unlock", json={"code": "wrong"}, headers=headers).status_code == 429
    assert unlock(hosted, headers=headers).status_code == 429
    # Rotating the client-controlled first hop does not evade the limit.
    assert unlock(hosted, headers={"X-Forwarded-For": "203.0.113.5, 192.0.2.2"}).status_code == 429
    assert unlock(hosted, headers={"X-Forwarded-For": "192.0.2.1"}).status_code == 200
    with live_access.database() as db:
        db.execute("UPDATE failures SET at=at-3601")
    assert unlock(hosted, headers=headers).status_code == 200


def test_cookie_persistence_expiry_and_secure(hosted, monkeypatch):
    response = unlock(hosted, headers={"X-Forwarded-Proto": "https"})
    cookie = response.headers["set-cookie"]
    for part in ("HttpOnly", "SameSite=lax", "Secure", "Max-Age=2592000"):
        assert part in cookie
    assert "private-judge-code" not in cookie
    token = response.cookies["live_session"]
    importlib.reload(live_access)
    with TestClient(app) as restarted:
        restarted.cookies.set("live_session", token)
        assert restarted.get("/api/config").json()["live_unlocked"] is True
        with live_access.database() as db:
            assert token not in str(db.execute("SELECT * FROM sessions").fetchall())
            db.execute("UPDATE sessions SET expires=0")
        assert restarted.get("/api/config").json()["live_unlocked"] is False
    assert "Secure" not in unlock(hosted).headers["set-cookie"]


def test_live_real_pipeline_mocked_transport_and_cap(hosted, monkeypatch):
    import httpx

    monkeypatch.setenv("LIVE_DAILY_CAP", "1")
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    calls = []
    extraction = {"flight_number": "LO123", "departure_airport": "WAW", "arrival_airport": "CDG", "disruption_type": "cancellation", "notice_days": 2}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        data = {"results": []} if "tavily" in url else {"choices": [{"message": {"content": json.dumps(extraction)}}]}
        return httpx.Response(200, json=data, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("groundcontrol.clients.record_fixture", lambda *a: pytest.fail("hosted request recorded input"))
    assert unlock(hosted).status_code == 200
    response = hosted.post("/api/live/run", json={"text": "My own flight was cancelled"})
    assert response.status_code == 200
    assert response.json()["mode"] == "live"
    assert any("tavily" in url for url, _ in calls)
    nemotron = next(kwargs for url, kwargs in calls if "tavily" not in url)
    assert nemotron["json"]["messages"][1]["content"] == "My own flight was cancelled"
    before = len(calls)
    response = hosted.post("/api/run", json={"text": "Another flight"})
    assert response.status_code == 429
    assert response.json() == {"error": "live_daily_cap"}
    importlib.reload(live_access)
    assert not live_access.reserve_run()
    assert len(calls) == before
    assert hosted.post("/api/run", json={"scenario_id": SCENARIO_IDS[0]}).status_code == 200
    with live_access.database() as db:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        db.execute("UPDATE runs SET day=?", (yesterday,))
    assert live_access.reserve_run()


def test_concurrent_cap(hosted, monkeypatch):
    monkeypatch.setenv("LIVE_DAILY_CAP", "3")
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: live_access.reserve_run(), range(16))) == 3


@pytest.mark.parametrize("name", ["JUDGE_CODE", "NEBIUS_API_KEY", "TAVILY_API_KEY", "LIVE"])
def test_missing_config_disables_live(hosted, monkeypatch, name):
    monkeypatch.delenv(name)
    assert hosted.get("/api/config").json() == {"live_available": False, "live_unlocked": False}
    assert unlock(hosted).status_code == 401
    assert hosted.post("/api/live/run", json={"text": "own"}).status_code == 401


def test_config_and_errors_no_secrets(hosted, monkeypatch):
    monkeypatch.setenv("NEMOTRON_MODEL", "private-nebius-key")
    assert hosted.get("/api/config").json() == {"live_available": True, "live_unlocked": False}
    for path in ("/api/config", "/api/info", "/"):
        response = hosted.get(path)
        assert all(secret not in response.text for secret in ("private-judge-code", "private-nebius-key", "private-tavily-key"))
    response = hosted.post("/api/run", json={"code": "private-judge-code"})
    assert response.status_code == 422
    assert "private-judge-code" not in response.text


@pytest.mark.parametrize("scenario", SCENARIO_IDS)
def test_hosted_replay_needs_no_code_or_network(hosted, scenario):
    result = hosted.post("/api/run", json={"scenario_id": scenario})
    assert result.status_code == 200
    assert result.json()["mode"] == "offline"


def test_live_errors_and_echoed_secrets_never_escape(hosted, monkeypatch):
    import httpx
    from groundcontrol import pipeline
    from groundcontrol.clients import UpstreamError

    assert unlock(hosted).status_code == 200

    def fail(*args, **kwargs):
        raise UpstreamError("private-nebius-key private-judge-code model input")

    monkeypatch.setattr(httpx, "post", fail)
    response = hosted.post("/api/live/run", json={"text": "private input"})
    assert response.status_code == 502
    assert "private" not in response.text

    # Save the real function because run_scenario itself calls pipeline.run.
    original_run = pipeline.run

    def echo_result(text):
        from groundcontrol.config import WEB_MODE
        from groundcontrol.clients import get_fixtures_dir
        mode = WEB_MODE.set(False)
        try:
            scenario = json.loads((get_fixtures_dir() / "scenarios" / f"{SCENARIO_IDS[0]}.json").read_text())
            result = original_run(scenario["input_text"])
        finally:
            WEB_MODE.reset(mode)
        result.claim = "private-nebius-key private-tavily-key private-judge-code"
        return result

    monkeypatch.setattr(pipeline, "run", echo_result)
    response = hosted.post("/api/live/run", json={"text": "own"})
    assert response.status_code == 200
    assert response.json()["claim"] == "[redacted] [redacted] [redacted]"
