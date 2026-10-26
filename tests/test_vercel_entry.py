"""The Vercel entrypoint must serve recorded replays only, whatever the environment says."""
import fnmatch
import importlib
import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


def test_entry_forces_offline_even_with_live_env(monkeypatch):
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "should-not-be-used")
    monkeypatch.setenv("TAVILY_API_KEY", "should-not-be-used")
    monkeypatch.delenv("GROUNDCONTROL_FIXTURES_DIR", raising=False)
    sys.modules.pop("app", None)
    entry = importlib.import_module("app")
    try:
        assert os.environ["LIVE"] == "0"
        assert Path(os.environ["GROUNDCONTROL_FIXTURES_DIR"]) == ROOT / "fixtures"
        with TestClient(entry.app) as client:
            assert client.get("/api/info").json()["mode"] == "offline"
            result = client.post("/api/run", json={"scenario_id": "delay-weather"}).json()
            compensation = result["assessment"]["compensation"]
            assert result["mode"] == "offline"
            assert compensation["amount_eur"] == 600 and compensation["disputed"]
            assert compensation["status"] == "verified"
            assert client.post("/api/run", json={"text": "No recorded fixture for this."}).status_code == 409
            assert "GroundControl" in client.get("/").text
    finally:
        sys.modules.pop("app", None)
        os.environ.pop("GROUNDCONTROL_FIXTURES_DIR", None)


def test_bundle_ships_code_and_fixtures_but_no_dev_files():
    config = json.loads((ROOT / "vercel.json").read_text())
    include = config["functions"]["app.py"]["includeFiles"]
    assert include == "{groundcontrol/**,fixtures/**}"
    ignored = [line for line in (ROOT / ".vercelignore").read_text().splitlines() if line and not line.startswith("#")]
    for shipped in ("groundcontrol/web.py", "groundcontrol/static/index.html", "fixtures/scenarios/delay-weather.json", "app.py"):
        assert not any(fnmatch.fnmatch(shipped, pat) or shipped.startswith(pat.rstrip("/") + "/") for pat in ignored), shipped
    for dropped in ("tests", "scripts", "docs", ".venv", "**/.env*", "**/*secret*"):
        assert dropped in ignored
