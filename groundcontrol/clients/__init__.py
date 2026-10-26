"""Replay and API clients for LLM and search services."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class FixtureMissing(Exception):
    """Raised when an offline fixture is missing for a requested call."""
    pass


class UpstreamError(Exception):
    """Raised when a live service (Token Factory, Tavily) is unreachable, rejects the call or replies malformed."""


class MissingApiKey(UpstreamError, ValueError):
    """Raised when LIVE=1 but the API key for a service is not configured."""


def post_json(service: str, url: str, **kwargs) -> dict:
    """POST to a live service and return the JSON body, mapping every transport/HTTP/JSON failure to UpstreamError."""
    import httpx

    try:
        resp = httpx.post(url, **kwargs)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        raise UpstreamError(f"{service} returned HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        raise UpstreamError(f"{service} is unreachable ({type(e).__name__})") from e
    except ValueError as e:
        raise UpstreamError(f"{service} returned a non-JSON response") from e
    if not isinstance(data, dict):
        raise UpstreamError(f"{service} returned an unexpected response")
    return data


def stable_hash(payload: dict) -> str:
    """Return a deterministic 16-character hex hash of a request payload."""
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def get_fixtures_dir() -> Path:
    """Return the Path to the root fixtures directory."""
    if fixtures_dir := os.environ.get("GROUNDCONTROL_FIXTURES_DIR"):
        return Path(fixtures_dir)
    # groundcontrol/clients/__init__.py -> root is 3 levels up
    return Path(__file__).resolve().parents[2] / "fixtures"


_RECORDER_HOOK = None


def set_recorder_hook(hook) -> None:
    """Set an optional module-level recording hook callable(kind, req_hash, payload, response)."""
    global _RECORDER_HOOK
    _RECORDER_HOOK = hook


def is_recording() -> bool:
    """Return True if fixture recording is enabled via env var or module hook."""
    from groundcontrol.config import WEB_MODE

    return WEB_MODE.get() is None and (os.environ.get("RECORD_FIXTURES", "0") == "1" or _RECORDER_HOOK is not None)


def record_fixture(kind: str, req_hash: str, payload: dict, response: object) -> None:
    """Save a live request/response to fixtures/<kind>/<req_hash>.json with recorded=true."""
    if _RECORDER_HOOK is not None:
        _RECORDER_HOOK(kind, req_hash, payload, response)
        return

    fixtures_dir = get_fixtures_dir()
    target_dir = fixtures_dir / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = target_dir / f"{req_hash}.json"

    # Ensure api_key is never in the stored request
    clean_payload = {k: v for k, v in payload.items() if k != "api_key"}

    fixture_data = {
        "recorded": True,
        "request": clean_payload,
        "response": response,
    }
    fixture_path.write_text(json.dumps(fixture_data, indent=2, sort_keys=True), encoding="utf-8")
