"""Fact extraction from free text inputs using Nemotron."""
from __future__ import annotations

import json
import re
from groundcontrol.airports import AIRPORTS
from groundcontrol.clients.nemotron import NemotronClient
from groundcontrol.models import FlightFacts

EXTRACTION_SYSTEM_PROMPT = (
    "You are a flight disruption analyzer for EU261 passenger claims. Extract the flight facts from the input text into a strict JSON object.\n"
    "All 15 keys must always be present in the output JSON object; use null when a value is unknown or unstated.\n\n"
    "Schema and Field Definitions:\n"
    "- flight_number: string or null (e.g. 'VQ101')\n"
    "- carrier: string or null (operating carrier code or name, e.g. 'VQ' or 'Vistula Air')\n"
    "- departure_airport: string or null (3-letter IATA code uppercase, e.g. 'WAW')\n"
    "- arrival_airport: string or null (3-letter IATA code uppercase, e.g. 'CDG')\n"
    "- scheduled_departure: string or null (local time ISO-8601, e.g. '2026-05-15T10:00:00')\n"
    "- scheduled_arrival: string or null (local time ISO-8601, e.g. '2026-05-15T13:30:00')\n"
    "- actual_arrival: string or null (local time ISO-8601, e.g. '2026-05-15T17:10:00')\n"
    "- disruption_type: string or null ('delay' or 'cancellation')\n"
    "- stated_reason: string or null (stated disruption reason)\n"
    "- notice_days: integer or null (days between notice and scheduled departure only if stated)\n"
    "- reroute_departs_early_min: integer or null (minutes departed early on reroute)\n"
    "- reroute_arrives_late_min: integer or null (minutes arrived late on reroute)\n"
    "- departure_delay_min: integer or null (departure delay in minutes)\n"
    "- arrival_delay_min: integer or null (compute arrival_delay_min only if both scheduled and actual arrival are stated)\n"
    "- passenger_name: string or null\n\n"
    "Rules:\n"
    "1. Exact JSON schema: all 15 keys must always be present (null when unknown).\n"
    "2. IATA codes uppercase.\n"
    "3. Times ISO-8601 local.\n"
    "4. Integers for minutes/days.\n"
    "5. Compute arrival_delay_min only if both scheduled and actual arrival are stated.\n"
    "6. Never guess.\n"
    "7. notice_days = days between notice and scheduled departure only if stated.\n"
    "8. No prose / no markdown. Respond with only the JSON object."
)


def _clean_str(val: object) -> str | None:
    if val is None or not isinstance(val, str):
        return None
    s = val.strip()
    return s if s else None


def _clean_int(val: object) -> int | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_json_object(raw: str) -> dict | None:
    """Extract and parse the first top-level JSON object from text, tolerating markdown and prose."""
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = raw.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(raw)):
        ch = raw[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : i + 1]
                try:
                    data = json.loads(candidate)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
                break

    return None


def extract_facts(text: str) -> FlightFacts:
    """Extract and validate FlightFacts from unstructured text."""
    client = NemotronClient()
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    raw_response = client.chat(messages, response_format={"type": "json_object"})
    data = parse_json_object(raw_response)

    if data is None:
        retry_messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": text},
            {"role": "assistant", "content": raw_response},
            {"role": "user", "content": "Your previous reply was not a valid JSON object. Reply with only the JSON object."},
        ]
        retry_response = client.chat(retry_messages, response_format={"type": "json_object"})
        data = parse_json_object(retry_response)
        if data is None:
            return FlightFacts()

    dep = _clean_str(data.get("departure_airport"))
    if dep:
        dep = dep.upper()
        if dep not in AIRPORTS:
            dep = None

    arr = _clean_str(data.get("arrival_airport"))
    if arr:
        arr = arr.upper()
        if arr not in AIRPORTS:
            arr = None

    disruption = _clean_str(data.get("disruption_type"))
    if disruption:
        disruption = disruption.lower()
        if disruption not in ("delay", "cancellation"):
            disruption = None

    return FlightFacts(
        flight_number=_clean_str(data.get("flight_number")),
        carrier=_clean_str(data.get("carrier")),
        departure_airport=dep,
        arrival_airport=arr,
        scheduled_departure=_clean_str(data.get("scheduled_departure")),
        scheduled_arrival=_clean_str(data.get("scheduled_arrival")),
        actual_arrival=_clean_str(data.get("actual_arrival")),
        disruption_type=disruption,
        stated_reason=_clean_str(data.get("stated_reason")),
        notice_days=_clean_int(data.get("notice_days")),
        reroute_departs_early_min=_clean_int(data.get("reroute_departs_early_min")),
        reroute_arrives_late_min=_clean_int(data.get("reroute_arrives_late_min")),
        departure_delay_min=_clean_int(data.get("departure_delay_min")),
        arrival_delay_min=_clean_int(data.get("arrival_delay_min")),
        passenger_name=_clean_str(data.get("passenger_name")),
    )
