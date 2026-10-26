"""End-to-end pipeline connecting extraction, assessment, verification, and drafting."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from groundcontrol.clients import get_fixtures_dir
from groundcontrol.drafts import render_claim, render_complaint
from groundcontrol.eu261 import assess
from groundcontrol.extract import extract_facts
from groundcontrol.models import Assessment, FlightFacts
from groundcontrol.verify import verify


@dataclass
class Result:
    facts: FlightFacts
    assessment: Assessment
    claim: str
    complaint: str


def run(text: str) -> Result:
    """Run end-to-end processing pipeline on input text."""
    facts = extract_facts(text)
    assessment = assess(facts)
    if assessment.applies:
        assessment = verify(assessment)
    claim = render_claim(assessment, facts)
    complaint = render_complaint(assessment, facts)
    return Result(
        facts=facts,
        assessment=assessment,
        claim=claim,
        complaint=complaint,
    )


def run_scenario(scenario_id: str) -> Result:
    """Load a scenario from fixtures/scenarios and run it through the pipeline."""
    scenario_path = get_fixtures_dir() / "scenarios" / f"{scenario_id}.json"
    if not scenario_path.is_file():
        raise FileNotFoundError(f"Scenario file not found: {scenario_path}")
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    input_text = data["input_text"]
    return run(input_text)
