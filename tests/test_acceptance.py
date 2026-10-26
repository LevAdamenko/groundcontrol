"""Frozen acceptance tests for the offline core (written by the planner; do not edit).

They pin the public contract described in docs/ARCHITECTURE.md.
"""
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from groundcontrol import eu261, pipeline, drafts
from groundcontrol.clients.tavily import TavilyClient
from groundcontrol.clients import FixtureMissing

ROOT = Path(__file__).resolve().parent.parent


# --- bands (Art. 7(1)) -------------------------------------------------------

@pytest.mark.parametrize(
    "km, intra, expected",
    [
        (1500, False, 250),
        (1501, False, 400),
        (3500, False, 400),
        (3501, False, 600),
        (3501, True, 400),
        (1501, True, 400),
        (1500, True, 250),
    ],
)
def test_compensation_band(km, intra, expected):
    assert eu261.compensation_band(km, intra_area=True if intra else False) == expected


# --- delay (Sturgeon) --------------------------------------------------------

@pytest.mark.parametrize(
    "km, intra, delay_min, expected",
    [
        (1000, True, 179, 0),
        (1000, True, 180, 250),
        (2000, True, 180, 400),
        (5000, False, 179, 0),
        (5000, False, 180, 300),
        (5000, False, 239, 300),
        (5000, False, 240, 600),
        (5000, True, 200, 400),
    ],
)
def test_delay_compensation(km, intra, delay_min, expected):
    assert eu261.delay_compensation(km, intra_area=intra, arrival_delay_min=delay_min) == expected


# --- cancellation (Art. 5(1)(c), Art. 7(2)) ----------------------------------

def test_cancellation_notice_14_days_no_compensation():
    assert eu261.cancellation_compensation(1000, intra_area=True, notice_days=14) == 0


def test_cancellation_notice_13_days_no_rerouting():
    assert eu261.cancellation_compensation(1000, intra_area=True, notice_days=13) == 250


def test_cancellation_7_13_days_good_rerouting_exempt():
    assert eu261.cancellation_compensation(
        1000, intra_area=True, notice_days=10,
        reroute_departs_early_min=120, reroute_arrives_late_min=239,
    ) == 0


def test_cancellation_7_13_days_rerouting_too_late():
    # arrives 4 h late: not "less than 4 h", so compensation owed; 240 min > 2 h → no reduction
    assert eu261.cancellation_compensation(
        1000, intra_area=True, notice_days=10,
        reroute_departs_early_min=0, reroute_arrives_late_min=240,
    ) == 250


def test_cancellation_under_7_days_rerouting_reduction():
    # told 3 days before, rerouted, arrives 3 h late on a 600 € flight: owed, 50 % → 300
    assert eu261.cancellation_compensation(
        6000, intra_area=False, notice_days=3,
        reroute_departs_early_min=0, reroute_arrives_late_min=180,
    ) == 300


def test_great_circle_waw_cdg():
    km = eu261.great_circle_km("WAW", "CDG")
    assert 1300 < km < 1450


# --- scenarios end to end, offline --------------------------------------------

EXPECTED = {
    "cancel-short-notice": (True, 400, False),
    "delay-3h40": (True, 250, False),
    "delay-weather": (True, 600, True),
    "longhaul-3h30": (True, 300, False),
    "outside-scope": (False, 0, False),
}


@pytest.mark.parametrize("scenario_id", sorted(EXPECTED))
def test_scenario_offline(scenario_id, monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    applies, amount, disputed = EXPECTED[scenario_id]
    result = pipeline.run_scenario(scenario_id)
    a = result.assessment
    assert a.applies is applies
    comp = a.compensation
    if not applies:
        assert comp is None or comp.amount_eur == 0
        assert a.not_applicable_reason
        return
    assert comp.amount_eur == amount
    assert comp.disputed is disputed
    assert comp.calculation is not None and comp.calculation.distance_km > 0
    assert comp.status == "verified"
    assert all(ev.url.split("/")[2].endswith(tuple(drafts.ALLOWED_DOMAINS)) for ev in comp.evidence)


# --- no proof, no claim --------------------------------------------------------

def test_claim_without_evidence_is_unverified(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    result = pipeline.run_scenario("delay-3h40")
    comp = result.assessment.compensation
    stripped = dataclasses.replace(comp, evidence=[])
    assert stripped.status == "unverified"
    letter = drafts.render_claim(dataclasses.replace(result.assessment, compensation=stripped), result.facts)
    assert "not verified" in letter.lower()


def test_claim_without_calculation_is_unverified(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    result = pipeline.run_scenario("delay-3h40")
    comp = result.assessment.compensation
    stripped = dataclasses.replace(comp, calculation=None)
    assert stripped.status == "unverified"


def test_evidence_outside_allowlist_is_dropped():
    from groundcontrol.verify import filter_evidence
    raw = [
        {"url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj", "content": "EUR 250 for all flights of 1500 kilometres or less"},
        {"url": "https://flight-claims-blog.example.com/eu261", "content": "EUR 250 for all flights of 1500 kilometres or less"},
    ]
    kept = filter_evidence(raw, anchor="EUR 250")
    assert [e.url for e in kept] == ["https://eur-lex.europa.eu/eli/reg/2004/261/oj"]


def test_missing_fixture_raises(monkeypatch):
    monkeypatch.setenv("LIVE", "0")
    with pytest.raises(FixtureMissing):
        TavilyClient().search("a query nobody recorded 7f3a", include_domains=["europa.eu"])


def test_demo_cli_offline():
    env = {k: v for k, v in os.environ.items() if k not in ("NEBIUS_API_KEY", "TAVILY_API_KEY")}
    env["LIVE"] = "0"
    out = subprocess.run(
        [sys.executable, "-m", "groundcontrol.demo", "--offline"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    for sid in EXPECTED:
        assert sid in out.stdout
