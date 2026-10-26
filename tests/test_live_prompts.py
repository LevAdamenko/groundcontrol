"""Tests for production extraction prompt, robust parsing, retry path, and fixture recording."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from groundcontrol import config, extract
from groundcontrol.clients import get_fixtures_dir
from groundcontrol.extract import EXTRACTION_SYSTEM_PROMPT, extract_facts, parse_json_object
from groundcontrol.models import FlightFacts
from scripts import record_fixtures
from scripts.make_fixtures import DOUBLE_INVALID_INPUT, RETRY_FACTS, RETRY_TEST_INPUT


def test_prompt_contains_every_flightfacts_field():
    """Verify EXTRACTION_SYSTEM_PROMPT mentions every single field of FlightFacts."""
    for f in dataclasses.fields(FlightFacts):
        assert f.name in EXTRACTION_SYSTEM_PROMPT, f"Missing field in prompt: {f.name}"


def test_parsing_tolerates_fences_and_prose():
    """Test that parse_json_object extracts JSON even with markdown fences or surrounding prose."""
    sample = {"flight_number": "VQ101", "carrier": "VQ", "departure_airport": "WAW"}

    # Plain JSON
    raw_plain = json.dumps(sample)
    assert parse_json_object(raw_plain) == sample

    # ```json ... ``` code fence
    raw_fence_json = f"```json\n{json.dumps(sample, indent=2)}\n```"
    assert parse_json_object(raw_fence_json) == sample

    # ``` ... ``` generic fence
    raw_fence = f"```\n{json.dumps(sample)}\n```"
    assert parse_json_object(raw_fence) == sample

    # Leading prose
    raw_leading = f"Here is the parsed flight disruption information:\n{json.dumps(sample)}"
    assert parse_json_object(raw_leading) == sample

    # Trailing prose
    raw_trailing = f"{json.dumps(sample)}\nI hope this information is helpful for your claim."
    assert parse_json_object(raw_trailing) == sample

    # Surrounding prose + fences
    raw_surrounded = f"Analysis result:\n```json\n{json.dumps(sample)}\n```\nPlease review."
    assert parse_json_object(raw_surrounded) == sample

    # Handles nested objects and braces inside strings
    nested = {
        "flight_number": "VQ101",
        "details": {"notes": "brace { inside string } and extra } brace"},
    }
    raw_nested = f"Prefix:\n{json.dumps(nested)}\nSuffix"
    assert parse_json_object(raw_nested) == nested

    # Invalid input / non-dict returns None
    assert parse_json_object("Just plain text with no json") is None
    assert parse_json_object("[1, 2, 3]") is None
    assert parse_json_object("{invalid json:") is None


def test_retry_path_offline(monkeypatch):
    """Offline test: first reply invalid -> second fixture valid -> facts filled."""
    monkeypatch.setenv("LIVE", "0")
    facts = extract_facts(RETRY_TEST_INPUT)

    assert facts.flight_number == RETRY_FACTS["flight_number"]
    assert facts.carrier == RETRY_FACTS["carrier"]
    assert facts.departure_airport == RETRY_FACTS["departure_airport"]
    assert facts.arrival_airport == RETRY_FACTS["arrival_airport"]
    assert facts.arrival_delay_min == RETRY_FACTS["arrival_delay_min"]
    assert facts.passenger_name == RETRY_FACTS["passenger_name"]


def test_double_invalid_returns_empty_flightfacts(monkeypatch):
    """Offline test: both first and retry replies invalid -> returns empty FlightFacts."""
    monkeypatch.setenv("LIVE", "0")
    facts = extract_facts(DOUBLE_INVALID_INPUT)

    assert facts == FlightFacts()
    assert facts.flight_number is None
    assert facts.carrier is None
    assert facts.departure_airport is None


def test_recorder_exits_2_without_live_or_keys(tmp_path, monkeypatch):
    """Verify record_fixtures exits code 2 and writes nothing without LIVE=1 or keys."""
    fake_fixtures_dir = tmp_path / "fixtures"
    fake_fixtures_dir.mkdir(parents=True)
    monkeypatch.setattr("groundcontrol.clients.get_fixtures_dir", lambda: fake_fixtures_dir)
    monkeypatch.setattr("scripts.record_fixtures.get_fixtures_dir", lambda: fake_fixtures_dir)

    # 1. LIVE=0 with keys and real scenarios present: the LIVE gate alone must stop it
    import shutil
    from pathlib import Path

    shutil.copytree(Path(__file__).resolve().parents[1] / "fixtures" / "scenarios", fake_fixtures_dir / "scenarios")
    monkeypatch.setenv("LIVE", "0")
    monkeypatch.setenv("NEBIUS_API_KEY", "key1")
    monkeypatch.setenv("TAVILY_API_KEY", "key2")
    with pytest.raises(SystemExit) as exc:
        record_fixtures.main([])
    assert exc.value.code == 2
    assert [p.name for p in fake_fixtures_dir.iterdir()] == ["scenarios"]
    shutil.rmtree(fake_fixtures_dir / "scenarios")

    # 2. LIVE=1 but missing NEBIUS_API_KEY
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "key2")
    with pytest.raises(SystemExit) as exc:
        record_fixtures.main([])
    assert exc.value.code == 2
    assert list(fake_fixtures_dir.iterdir()) == []

    # 3. LIVE=1, NEBIUS_API_KEY present, but missing TAVILY_API_KEY
    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", "key1")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        record_fixtures.main([])
    assert exc.value.code == 2
    assert list(fake_fixtures_dir.iterdir()) == []


def test_recorder_never_stores_api_key(tmp_path, monkeypatch):
    """Unit test with mocked httpx: LIVE=1, fake keys, verifies api_key never written."""
    fake_nebius_key = "secret-nebius-key-value-999"
    fake_tavily_key = "secret-tavily-key-value-888"

    monkeypatch.setenv("LIVE", "1")
    monkeypatch.setenv("NEBIUS_API_KEY", fake_nebius_key)
    monkeypatch.setenv("TAVILY_API_KEY", fake_tavily_key)
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)

    # Set up tmp fixtures directory with real scenarios
    fixtures_real = get_fixtures_dir()
    fake_fixtures_dir = tmp_path / "fixtures"
    fake_fixtures_dir.mkdir(parents=True)
    shutil.copytree(fixtures_real / "scenarios", fake_fixtures_dir / "scenarios")

    monkeypatch.setattr("groundcontrol.clients.get_fixtures_dir", lambda: fake_fixtures_dir)
    monkeypatch.setattr("scripts.record_fixtures.get_fixtures_dir", lambda: fake_fixtures_dir)

    extraction_content = json.dumps({
        "flight_number": "VQ101",
        "carrier": "VQ",
        "departure_airport": "WAW",
        "arrival_airport": "CDG",
        "scheduled_departure": "2026-06-10T14:00:00",
        "scheduled_arrival": "2026-06-10T16:30:00",
        "actual_arrival": "2026-06-10T20:10:00",
        "disruption_type": "delay",
        "stated_reason": "Technical fault",
        "notice_days": None,
        "reroute_departs_early_min": None,
        "reroute_arrives_late_min": None,
        "departure_delay_min": 220,
        "arrival_delay_min": 220,
        "passenger_name": "Test Passenger",
    })

    narrative_content = "On June 10, 2026, my flight VQ101 from Warsaw to Paris was delayed by 220 minutes due to technical faults."

    def fake_post(url, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        json_body = kwargs.get("json", {})
        if "chat/completions" in url:
            # Check if this is an extraction or narrative call
            messages = json_body.get("messages", [])
            is_extraction = any("Extract the flight facts" in m.get("content", "") for m in messages)
            reply = extraction_content if is_extraction else narrative_content
            mock_resp.json.return_value = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": reply}}],
            }
        elif "tavily.com" in url:
            mock_resp.json.return_value = {
                "query": json_body.get("query", ""),
                "results": [
                    {
                        "url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj",
                        "title": "Regulation (EC) No 261/2004",
                        "content": "EUR 250 EUR 400 EUR 600 meals and refreshments reimbursement three hours or more",
                    }
                ],
            }
        else:
            mock_resp.json.return_value = {}
        return mock_resp

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    exit_code = record_fixtures.main([])
    assert exit_code == 0
    assert os.environ.get("RECORD_FIXTURES") is None, "recording must not leak past main()"

    nemotron_files = list((fake_fixtures_dir / "nemotron").glob("*.json"))
    tavily_files = list((fake_fixtures_dir / "tavily").glob("*.json"))

    assert len(nemotron_files) > 0, "No nemotron fixtures were recorded"
    assert len(tavily_files) > 0, "No tavily fixtures were recorded"

    for p in nemotron_files + tavily_files:
        text = p.read_text(encoding="utf-8")
        assert fake_nebius_key not in text, f"Nebius API key leaked in {p.name}"
        assert fake_tavily_key not in text, f"Tavily API key leaked in {p.name}"

        data = json.loads(text)
        assert data.get("recorded") is True, f"Recorded flag not True in {p.name}"
        req = data.get("request", {})
        assert "api_key" not in req, f"'api_key' found in request payload of {p.name}"
        assert "api_key" not in json.dumps(req), f"'api_key' substring found in request payload of {p.name}"
