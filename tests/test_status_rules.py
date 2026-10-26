"""Status rules: assumed inputs and partially backed amounts are never "verified"."""
from groundcontrol import eu261
from groundcontrol.models import Calculation, Entitlement, Evidence, FlightFacts

EUR_600 = Evidence(
    url="https://eur-lex.europa.eu/eli/reg/2004/261/oj",
    title="Regulation (EC) No 261/2004",
    snippet="(c) EUR 600 for all flights not falling under (a) or (b).",
    anchor="EUR 600",
)
STURGEON = Evidence(
    url="https://curia.europa.eu/juris/liste.jsf?num=C-402/07",
    title="Sturgeon, C-402/07",
    snippet="a loss of time equal to or in excess of three hours, that is, when they reach their final destination three hours or more after the arrival time",
    anchor="three hours or more",
)


def _reduced_300(evidence: list[Evidence]) -> Entitlement:
    return Entitlement(
        kind="compensation",
        amount_eur=300,
        calculation=Calculation(distance_km=6850, arrival_delay_min=210, band_eur=600, reduction_applied=True),
        evidence=evidence,
        required_anchors=["EUR 600", "three hours or more"],
    )


def test_300_needs_both_band_and_sturgeon_sources():
    assert _reduced_300([EUR_600, STURGEON]).status == "verified"
    assert _reduced_300([STURGEON]).status == "unverified"
    assert _reduced_300([EUR_600]).status == "unverified"


def test_required_anchor_must_match_the_evidence_anchor():
    # A Sturgeon snippet that happens to mention "EUR 600" does not count as the band source.
    mixed = Evidence(url=STURGEON.url, title=STURGEON.title, snippet=STURGEON.snippet + " EUR 600", anchor="three hours or more")
    assert _reduced_300([mixed]).status == "unverified"


def test_cancellation_without_notice_is_provisional_and_unverified():
    facts = FlightFacts(
        flight_number="VQ401",
        carrier="VQ",
        departure_airport="WAW",
        arrival_airport="LIS",
        disruption_type="cancellation",
        notice_days=None,
    )
    a = eu261.assess(facts)
    assert "notice_days" in a.missing_facts
    comp = a.compensation
    assert comp.calculation.provisional is True
    comp.evidence = [Evidence(
        url="https://eur-lex.europa.eu/eli/reg/2004/261/oj",
        title="Regulation (EC) No 261/2004",
        snippet="(b) EUR 400 for all intra-Community flights of more than 1500 kilometres",
        anchor="EUR 400",
    )]
    comp.required_anchors = ["EUR 400"]
    assert comp.amount_eur == 400
    assert comp.status == "unverified"


def test_cancellation_with_stated_notice_is_not_provisional():
    facts = FlightFacts(
        flight_number="VQ401",
        carrier="VQ",
        departure_airport="WAW",
        arrival_airport="LIS",
        disruption_type="cancellation",
        notice_days=5,
    )
    assert eu261.assess(facts).compensation.calculation.provisional is False


def test_pipeline_300_drops_to_unverified_without_band_source():
    from groundcontrol import pipeline

    comp = pipeline.run_scenario("longhaul-3h30").assessment.compensation
    assert comp.amount_eur == 300
    assert comp.status == "verified"
    comp.evidence = [ev for ev in comp.evidence if ev.anchor != "EUR 600"]
    assert comp.status == "unverified"
