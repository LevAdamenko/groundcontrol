"""Unit tests for EU261 rules, boundaries, and scope logic."""
import pytest
from groundcontrol import eu261
from groundcontrol.models import FlightFacts


# --- Scope Tests (Article 3(1)) ---

def test_scope_eea_norway_departure():
    """EEA departure (Norway, OSL) to EU (CDG) must be in scope."""
    facts = FlightFacts(
        flight_number="VQ123",
        carrier="VQ",
        departure_airport="OSL",
        arrival_airport="CDG",
        disruption_type="delay",
        arrival_delay_min=200,
    )
    applies, reason = eu261.applies(facts)
    assert applies is True
    assert reason is None


def test_scope_non_eu_carrier_into_eu():
    """Non-EU carrier departing outside EU into EU is NOT in scope."""
    facts = FlightFacts(
        flight_number="GH101",
        carrier="GH",
        departure_airport="DXB",
        arrival_airport="WAW",
        disruption_type="delay",
        arrival_delay_min=240,
    )
    applies, reason = eu261.applies(facts)
    assert applies is False
    assert "not an EU261 carrier" in reason


def test_scope_eu_carrier_from_outside_into_eu():
    """EU carrier departing outside EU (JFK) into EU (WAW) IS in scope."""
    facts = FlightFacts(
        flight_number="VQ506",
        carrier="VQ",
        departure_airport="JFK",
        arrival_airport="WAW",
        disruption_type="delay",
        arrival_delay_min=200,
    )
    applies, reason = eu261.applies(facts)
    assert applies is True
    assert reason is None


def test_scope_uk_departure_eu_carrier_into_eu_applies():
    """UK is a third country: LHR -> WAW on an EU carrier is covered by Art. 3(1)(b)."""
    facts = FlightFacts(
        flight_number="VQ801",
        carrier="VQ",
        departure_airport="LHR",
        arrival_airport="WAW",
        disruption_type="cancellation",
        notice_days=2,
    )
    applies, reason = eu261.applies(facts)
    assert applies is True
    assert reason is None


def test_scope_uk_departure_non_eu_carrier_points_to_uk261():
    """LHR -> WAW on a non-EU carrier is outside EU261; the reason mentions UK261."""
    facts = FlightFacts(
        flight_number="GH801",
        carrier="GH",
        departure_airport="LHR",
        arrival_airport="WAW",
        disruption_type="cancellation",
        notice_days=2,
    )
    applies, reason = eu261.applies(facts)
    assert applies is False
    assert "UK261" in reason


def test_scope_both_outside_eu():
    """Flight entirely outside EU261 area is out of scope."""
    facts = FlightFacts(
        flight_number="GH202",
        carrier="GH",
        departure_airport="DXB",
        arrival_airport="JFK",
        disruption_type="delay",
        arrival_delay_min=300,
    )
    applies, reason = eu261.applies(facts)
    assert applies is False


# --- Compensation Band Boundaries (Article 7(1)) ---

def test_band_boundaries():
    assert eu261.compensation_band(1499, intra_area=False) == 250
    assert eu261.compensation_band(1500, intra_area=False) == 250
    assert eu261.compensation_band(1501, intra_area=False) == 400
    assert eu261.compensation_band(3500, intra_area=False) == 400
    assert eu261.compensation_band(3501, intra_area=False) == 600

    # Intra-area is always capped at 400 for > 1500 km
    assert eu261.compensation_band(4000, intra_area=True) == 400


# --- Cancellation Boundaries and Reductions (Article 5 & 7(2)) ---

def test_cancellation_14_days_or_more():
    assert eu261.cancellation_compensation(1000, intra_area=True, notice_days=14) == 0
    assert eu261.cancellation_compensation(1000, intra_area=True, notice_days=21) == 0


def test_cancellation_7_to_13_days():
    # Offered reroute: departs <= 2h early and arrives < 4h late -> 0
    assert eu261.cancellation_compensation(
        2000, intra_area=False, notice_days=7,
        reroute_departs_early_min=120, reroute_arrives_late_min=239,
    ) == 0

    # Arrives >= 4h late (240 min) -> compensation owed
    assert eu261.cancellation_compensation(
        2000, intra_area=False, notice_days=7,
        reroute_departs_early_min=60, reroute_arrives_late_min=240,
    ) == 400

    # Departs > 2h early (121 min), arrives > 3h late (200 min) -> full 400 owed
    assert eu261.cancellation_compensation(
        2000, intra_area=False, notice_days=10,
        reroute_departs_early_min=121, reroute_arrives_late_min=200,
    ) == 400

    # Departs > 2h early (121 min), but arrives <= 3h late (60 min) -> reduced 50% to 200
    assert eu261.cancellation_compensation(
        2000, intra_area=False, notice_days=10,
        reroute_departs_early_min=121, reroute_arrives_late_min=60,
    ) == 200


def test_cancellation_less_than_7_days():
    # Offered reroute: departs <= 1h early and arrives < 2h late -> 0
    assert eu261.cancellation_compensation(
        1000, intra_area=True, notice_days=3,
        reroute_departs_early_min=60, reroute_arrives_late_min=119,
    ) == 0

    # Departs > 1h early (61 min), arrives > 2h late (150 min) -> full 250 owed
    assert eu261.cancellation_compensation(
        1000, intra_area=True, notice_days=3,
        reroute_departs_early_min=61, reroute_arrives_late_min=150,
    ) == 250

    # Departs > 1h early (61 min), but arrives <= 2h late (60 min) -> reduced 50% to 125
    assert eu261.cancellation_compensation(
        1000, intra_area=True, notice_days=3,
        reroute_departs_early_min=61, reroute_arrives_late_min=60,
    ) == 125


def test_cancellation_50_percent_reductions():
    # 250 EUR band: arrives <= 2h late -> 125 EUR
    assert eu261.cancellation_compensation(
        1000, intra_area=True, notice_days=3,
        reroute_departs_early_min=90, reroute_arrives_late_min=120,
    ) == 125

    # 400 EUR band: arrives <= 3h late -> 200 EUR
    assert eu261.cancellation_compensation(
        2000, intra_area=False, notice_days=3,
        reroute_departs_early_min=90, reroute_arrives_late_min=180,
    ) == 200

    # 600 EUR band: arrives <= 4h late -> 300 EUR
    assert eu261.cancellation_compensation(
        6000, intra_area=False, notice_days=3,
        reroute_departs_early_min=90, reroute_arrives_late_min=240,
    ) == 300


# --- Extraordinary Circumstances and Reason Classification ---

def test_classify_reason_technical_fault():
    disputed, explanation = eu261.classify_reason("Technical defect in engine")
    assert disputed is False
    assert "C-549/07" in explanation
    assert "Wallentin-Hermann" in explanation


def test_classify_reason_internal_airline_strike():
    disputed, explanation = eu261.classify_reason("Pilot strike by company union")
    assert disputed is False
    assert "C-28/20" in explanation


def test_classify_reason_external_weather_and_atc():
    disputed, explanation = eu261.classify_reason("Severe thunderstorm and lightning")
    assert disputed is True
    assert "Article 5(3)" in explanation

    disputed_atc, explanation_atc = eu261.classify_reason("ATC restriction due to airspace closure")
    assert disputed_atc is True


# --- Assessment Care and Refund Entitlements ---

def test_care_and_refund_in_delay_assessment():
    facts = FlightFacts(
        flight_number="VQ505",
        carrier="VQ",
        departure_airport="WAW",
        arrival_airport="JFK",
        disruption_type="delay",
        arrival_delay_min=300,
        departure_delay_min=300,
        stated_reason="weather",
    )
    a = eu261.assess(facts)
    assert a.applies is True
    assert a.compensation is not None
    assert a.compensation.amount_eur == 600
    assert a.compensation.disputed is True
    assert len(a.care) > 0
    assert a.refund_or_rerouting is not None
    assert a.refund_or_rerouting.article == "Article 8"
