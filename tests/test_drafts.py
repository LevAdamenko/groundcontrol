import pytest
"""Tests for drafting logic, model narrative guard, and NEB complaints."""
import dataclasses
from groundcontrol import drafts
from groundcontrol.models import Assessment, Calculation, Entitlement, Evidence, FlightFacts



@pytest.fixture
def fixed_narrative(monkeypatch):
    # These tests check the letter template, not the model: the narrative is a fixed sentence.
    monkeypatch.setattr(drafts.NemotronClient, "chat", lambda self, messages, response_format=None: "My flight was disrupted.")


def test_euro_amount_extraction():
    text = "The airline offered 100 € on site, but I demand EUR 250 or 600 euros according to EU rules."
    amounts = drafts.extract_euro_amounts(text)
    assert amounts == [100, 250, 600]


def test_narrative_guard_replaces_mismatched_amount():
    hallucinated_prose = "I was delayed for hours and according to law I should receive EUR 600 immediately."
    guarded = drafts._guard_narrative(hallucinated_prose, expected_amount=250)
    assert guarded == drafts.DEFAULT_NEUTRAL_PROSE
    assert "EUR 600" not in guarded


def test_narrative_guard_preserves_matching_amount():
    correct_prose = "My flight was delayed by over 3 hours, entitling me to statutory compensation of EUR 250."
    guarded = drafts._guard_narrative(correct_prose, expected_amount=250)
    assert guarded == correct_prose


def test_narrative_guard_preserves_prose_without_euro_amounts():
    factual_prose = "The flight was delayed due to a hydraulic malfunction, arriving 4 hours late in Paris."
    guarded = drafts._guard_narrative(factual_prose, expected_amount=250)
    assert guarded == factual_prose


def test_claim_letter_unverified_marker(fixed_narrative):
    calc = Calculation(distance_km=1342, band_eur=250, article="Article 7")
    comp = Entitlement(
        kind="compensation",
        amount_eur=250,
        calculation=calc,
        evidence=[],  # No evidence -> unverified
    )
    assessment = Assessment(applies=True, compensation=comp)
    facts = FlightFacts(
        flight_number="VQ202",
        carrier="VQ",
        departure_airport="WAW",
        arrival_airport="CDG",
        disruption_type="delay",
        arrival_delay_min=220,
        stated_reason="Technical fault with aircraft hydraulic system",
        passenger_name="Jan Nowak",
    )
    letter = drafts.render_claim(assessment, facts)
    assert "(not verified against an official source)" in letter


def test_claim_letter_disputed_wording(fixed_narrative):
    calc = Calculation(distance_km=6860, band_eur=600, article="Article 7")
    ev = Evidence(
        url="https://eur-lex.europa.eu/eli/reg/2004/261/oj",
        title="Regulation 261/2004",
        snippet="EUR 600 for all flights not falling under (a) or (b)",
        anchor="EUR 600",
    )
    comp = Entitlement(
        kind="compensation",
        amount_eur=600,
        calculation=calc,
        evidence=[ev],
        disputed=True,
        disputed_reason="Thunderstorm",
    )
    assessment = Assessment(applies=True, compensation=comp)
    facts = FlightFacts(
        flight_number="VQ505",
        carrier="VQ",
        departure_airport="WAW",
        arrival_airport="JFK",
        disruption_type="delay",
        arrival_delay_min=300,
        stated_reason="Severe thunderstorm and lightning along the transatlantic flight route",
        passenger_name="Piotr Wiśniewski",
    )
    letter = drafts.render_claim(assessment, facts)
    assert "extraordinary circumstances" in letter.lower()
    assert "burden of proof" in letter.lower()


def test_complaint_letter_neb_table_and_prior_contact():
    facts_pl = FlightFacts(departure_airport="WAW", arrival_airport="CDG", carrier="VQ")
    complaint_pl = drafts.render_complaint(Assessment(applies=True), facts_pl)
    assert "Urząd Lotnictwa Cywilnego (ULC)" in complaint_pl
    assert "airline must be contacted first" in complaint_pl

    facts_de = FlightFacts(departure_airport="FRA", arrival_airport="WAW", carrier="VQ")
    complaint_de = drafts.render_complaint(Assessment(applies=True), facts_de)
    assert "Luftfahrt-Bundesamt (LBA)" in complaint_de

    facts_fr = FlightFacts(departure_airport="CDG", arrival_airport="WAW", carrier="VQ")
    complaint_fr = drafts.render_complaint(Assessment(applies=True), facts_fr)
    assert "Direction Générale de l'Aviation Civile (DGAC)" in complaint_fr


def test_narrative_prompt_timing(monkeypatch):
    captured = []

    def chat(self, messages):
        captured.append(messages)
        return "My flight was disrupted."

    monkeypatch.setattr(drafts.NemotronClient, "chat", chat)
    cases = [
        (FlightFacts(arrival_delay_min=210, departure_delay_min=90,
                     scheduled_departure="2026-06-10T14:00:00"), [
            "Arrival at the final destination was 210 minutes (3 h 30 min) later than scheduled.",
            "Departure was 90 minutes later than scheduled.",
            "Scheduled departure: 2026-06-10T14:00:00.",
        ], ["informed of the cancellation"]),
        (FlightFacts(disruption_type="cancellation", notice_days=5), [
            "The passenger was informed of the cancellation 5 days before the scheduled departure.",
        ], ["Arrival at the final destination", "Departure was", "Scheduled departure:"]),
        (FlightFacts(arrival_delay_min=0, departure_delay_min=0, notice_days=0), [
            "Arrival at the final destination was 0 minutes (0 h 0 min) later than scheduled.",
            "Departure was 0 minutes later than scheduled.",
            "The passenger was informed of the cancellation 0 days before the scheduled departure.",
        ], []),
        (FlightFacts(), [], ["Arrival at the final destination", "Departure was",
                             "informed of the cancellation", "Scheduled departure:"]),
    ]
    for facts, present, absent in cases:
        drafts._generate_narrative(facts, None)
        system, user = captured[-1]
        assert "Use every number exactly as given, with its unit; never turn an arrival delay into a departure delay or days into hours." in system["content"]
        assert "Delay / notice:" not in user["content"]
        assert "None" not in user["content"]
        for sentence in present:
            assert sentence in user["content"]
        for sentence in absent:
            assert sentence not in user["content"]
