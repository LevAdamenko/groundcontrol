"""Offline coverage for the web adapter."""
import json

import pytest
from fastapi.testclient import TestClient

from groundcontrol.clients import get_fixtures_dir
from groundcontrol.demo import SCENARIO_IDS
from groundcontrol.models import Calculation, Entitlement
from groundcontrol.web import MAX_TEXT_CHARS, OFFLINE_DETAIL, app, serialize_entitlement


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    with TestClient(app) as client:
        yield client


def test_scenarios(client):
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 5
    assert [item["id"] for item in items] == SCENARIO_IDS
    assert all(set(item) == {"id", "title", "input_text"} for item in items)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_run_scenarios(client, scenario_id):
    expected = json.loads((get_fixtures_dir() / "scenarios" / f"{scenario_id}.json").read_text())["expected"]
    response = client.post("/api/run", json={"scenario_id": scenario_id})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "offline"
    assessment = result["assessment"]
    compensation = assessment["compensation"]
    assert assessment["applies"] == expected["applies"]
    assert "verification_error" in assessment
    assert assessment["verification_error"] is None
    assert (compensation["amount_eur"] if compensation else 0) == expected["amount"]
    assert (compensation["disputed"] if compensation else False) == expected["disputed"]
    assert result["claim"] and result["complaint"]
    entitlements = assessment["care"] + ([compensation] if compensation else [])
    if assessment["refund_or_rerouting"]:
        entitlements.append(assessment["refund_or_rerouting"])
    for item in entitlements:
        assert item["status"] in ("verified", "unverified")
        assert {"calculation", "evidence", "disputed", "disputed_reason"} <= item.keys()
    if scenario_id == "delay-3h40":
        assert compensation["calculation"]["distance_km"] > 0
        assert {"distance_km", "arrival_delay_min", "notice_days", "band_eur", "reduction_applied", "article", "notes", "provisional"} <= set(compensation["calculation"])
        assert all(set(ev) == {"url", "title", "snippet", "anchor"} for ev in compensation["evidence"])
    if scenario_id == "outside-scope":
        assert assessment["not_applicable_reason"]


def test_missing_fixture(client):
    response = client.post("/api/run", json={"text": "An arbitrary flight with no recorded fixture."})
    assert response.status_code == 409
    assert response.json() == {"detail": OFFLINE_DETAIL}


@pytest.mark.parametrize("body", [{}, {"text": "test", "scenario_id": "delay-3h40"}, {"text": None}, {"scenario_id": None}, {"text": "test", "scenario_id": None}])
def test_invalid_request(client, body):
    assert client.post("/api/run", json=body).status_code == 422


def test_text_length_cap(client):
    assert client.post("/api/run", json={"text": "x" * MAX_TEXT_CHARS}).status_code == 409
    assert client.post("/api/run", json={"text": "x" * (MAX_TEXT_CHARS + 1)}).status_code == 422


def test_textarea_matches_text_cap(client):
    assert f'maxlength="{MAX_TEXT_CHARS}"' in client.get("/").text


@pytest.mark.parametrize("scenario_id", ["unknown", "../../README"])
def test_unknown_scenario(client, scenario_id):
    assert client.post("/api/run", json={"scenario_id": scenario_id}).status_code == 404


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Claim to airline" in response.text
    assert "Complaint to authority" in response.text


def test_status_property_without_evidence():
    entitlement = Entitlement(kind="compensation", calculation=Calculation(distance_km=1200))
    assert serialize_entitlement(entitlement)["status"] == entitlement.status == "unverified"


def test_recorded_text(client):
    scenario = client.get("/api/scenarios").json()[1]
    response = client.post("/api/run", json={"text": scenario["input_text"]})
    assert response.status_code == 200
    assert response.json()["assessment"]["compensation"]["amount_eur"] == 250


@pytest.fixture
def live_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JUDGE_CODE", "judge-test-code")
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "secret-nebius-key-123")
    monkeypatch.setenv("TAVILY_API_KEY", "secret-tavily-key-456")
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)
    with TestClient(app) as client:
        assert client.post("/api/unlock", json={"code": "judge-test-code"}).status_code == 200
        yield client


def _fake_post(response=None, error=None):
    import httpx

    def post(url, *args, **kwargs):
        if error is not None:
            raise error
        response.request = httpx.Request("POST", url)
        return response

    return post


def test_live_missing_key_locks_access(live_client, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY")
    response = live_client.post("/api/run", json={"text": "Flight LO123 was cancelled."})
    assert response.status_code == 401
    assert response.json() == {"error": "live_locked"}


def test_live_network_failure_is_502(live_client, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "post", _fake_post(error=httpx.ConnectError("boom")))
    response = live_client.post("/api/run", json={"text": "My cancelled flight"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Live service unavailable. Try again or pick a recorded flight."


@pytest.mark.parametrize("status", [401, 429, 503])
def test_live_http_error_is_502_without_key(live_client, monkeypatch, status):
    import httpx

    monkeypatch.setattr(httpx, "post", _fake_post(httpx.Response(status, json={"error": "nope"})))
    response = live_client.post("/api/run", json={"text": "Flight LO123 was cancelled."})
    assert response.status_code == 502
    assert "Live service unavailable" in response.json()["detail"]
    assert "secret" not in response.text


def test_live_malformed_completion_is_502(live_client, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "post", _fake_post(httpx.Response(200, json={"choices": []})))
    response = live_client.post("/api/run", json={"text": "Flight LO123 was cancelled."})
    assert response.status_code == 502
    assert "Live service unavailable" in response.json()["detail"]


def test_live_tavily_failure_degrades(live_client, monkeypatch):
    import httpx

    extraction = json.dumps({"flight_number": "LO123", "departure_airport": "WAW", "arrival_airport": "CDG", "disruption_type": "cancellation", "notice_days": 2})

    def post(url, *args, **kwargs):
        if "tavily" in url:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"choices": [{"message": {"content": extraction}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    response = live_client.post("/api/run", json={"text": "Flight LO123 was cancelled."})
    assert response.status_code == 200
    data = response.json()
    assert data["assessment"]["verification_error"] == "Official-source check unavailable"
    assert data["assessment"]["compensation"]["status"] == "unverified"


def test_live_tavily_missing_key_locks(live_client, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    response = live_client.post("/api/run", json={"text": "Flight LO123 was cancelled."})
    assert response.status_code == 401
    assert response.json() == {"error": "live_locked"}


def test_favicon(client):
    assert client.get("/favicon.ico").status_code == 204
    assert 'rel="icon"' in client.get("/").text


def test_info_does_not_expose_model_configuration(client, monkeypatch):
    monkeypatch.setenv("NEMOTRON_MODEL", "nvidia/test-model")
    assert client.get("/api/info").json() == {"mode": "offline"}
    assert "Nemotron via Nebius Token Factory" in client.get("/").text


def test_index_contains_mode_hint_and_verification_error(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "mode-hint" in response.text
    assert "verification_error" in response.text
