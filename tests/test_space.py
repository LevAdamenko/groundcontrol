"""Deployment configuration and fixture lookup checks."""
from pathlib import Path

from groundcontrol.clients import get_fixtures_dir


ROOT = Path(__file__).resolve().parents[1]


def test_fixtures_dir_default(monkeypatch):
    monkeypatch.delenv("GROUNDCONTROL_FIXTURES_DIR", raising=False)
    assert get_fixtures_dir() == ROOT / "fixtures"


def test_fixtures_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("GROUNDCONTROL_FIXTURES_DIR", str(tmp_path))
    assert get_fixtures_dir() == tmp_path


def test_docker_live_configuration():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "LIVE=1" in dockerfile
    assert "DATA_DIR=/data" in dockerfile
    assert "USER user" in dockerfile
    assert "groundcontrol.web:app" in dockerfile
    assert "app:app" not in dockerfile
    assert "PORT=7860" in dockerfile
    assert "EXPOSE 7860" in dockerfile
    assert "--port ${PORT:-7860}" in dockerfile
    assert "--no-access-log" in dockerfile
    assert ".env" in (ROOT / ".dockerignore").read_text()
