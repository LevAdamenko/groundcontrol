"""Draft generators for airline claims and National Enforcement Body complaints."""
from __future__ import annotations

import re
from groundcontrol.airports import get_airport
from groundcontrol.carriers import get_carrier
from groundcontrol.clients.nemotron import NemotronClient
from groundcontrol.models import Assessment, FlightFacts
from groundcontrol.verify import ALLOWED_DOMAINS  # re-exported as required

NEB_BODIES: dict[str, str] = {
    "PL": "Urząd Lotnictwa Cywilnego (ULC)",
    "DE": "Luftfahrt-Bundesamt (LBA)",
    "FR": "Direction Générale de l'Aviation Civile (DGAC)",
    "ES": "Agencia Estatal de Seguridad Aérea (AESA)",
    "PT": "Autoridade Nacional da Aviação Civil (ANAC)",
}

DEFAULT_NEUTRAL_PROSE = (
    "On the scheduled travel date, the aforementioned flight experienced a significant disruption "
    "resulting in a claim under Regulation (EC) No 261/2004."
)


def extract_euro_amounts(text: str) -> list[int]:
    """Extract all explicit euro amounts from text."""
    patterns = [
        r"€\s*(\d+)",
        r"(\d+)\s*€",
        r"\bEUR\s*(\d+)\b",
        r"\b(\d+)\s*EUR\b",
        r"\b(\d+)\s*euros?\b",
    ]
    amounts: list[int] = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            amounts.append(int(m.group(1)))
    return amounts


def _guard_narrative(narrative: str, expected_amount: int | None) -> str:
    """Guard against model hallucinated euro amounts."""
    extracted = extract_euro_amounts(narrative)
    if expected_amount is not None:
        for amt in extracted:
            if amt != expected_amount:
                return DEFAULT_NEUTRAL_PROSE
    elif extracted:
        return DEFAULT_NEUTRAL_PROSE
    return narrative.strip()


NARRATIVE_SYSTEM_PROMPT = (
    "You are an assistant drafting a concise, factual narrative statement of what happened "
    "for a flight disruption claim. Write 2–4 sentences in the first person. "
    "State only the facts of the disruption. Do not mention any euro amounts, do not include "
    "legal citations or references to regulations, and make no promises. "
    "Write only the paragraph, without greetings, pleasantries, or sign-offs. "
    "Use every number exactly as given, with its unit; never turn an arrival delay into a departure delay or days into hours."
)


def _generate_narrative(facts: FlightFacts, expected_amount: int | None) -> str:
    """Ask Nemotron for a short narrative paragraph and apply euro guard."""
    timing = []
    if facts.arrival_delay_min is not None:
        hours, minutes = divmod(facts.arrival_delay_min, 60)
        timing.append(
            f"Arrival at the final destination was {facts.arrival_delay_min} minutes "
            f"({hours} h {minutes} min) later than scheduled."
        )
    if facts.departure_delay_min is not None:
        timing.append(f"Departure was {facts.departure_delay_min} minutes later than scheduled.")
    if facts.notice_days is not None:
        timing.append(
            f"The passenger was informed of the cancellation {facts.notice_days} days "
            "before the scheduled departure."
        )
    if facts.scheduled_departure:
        timing.append(f"Scheduled departure: {facts.scheduled_departure}.")
    client = NemotronClient()
    messages = [
        {
            "role": "system",
            "content": NARRATIVE_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"Flight {facts.flight_number or 'N/A'} operated by {facts.carrier or 'the airline'} from "
                f"{facts.departure_airport or 'origin'} to {facts.arrival_airport or 'destination'}. "
                f"Disruption type: {facts.disruption_type or 'disruption'}. "
                f"Stated reason: {facts.stated_reason or 'unspecified'}. "
                + " ".join(timing)
            ),
        },
    ]
    raw_narrative = client.chat(messages)
    return _guard_narrative(raw_narrative, expected_amount)


def render_claim(assessment: Assessment, facts: FlightFacts) -> str:
    """Render a formal claim letter to the operating airline."""
    passenger = facts.passenger_name or "[Passenger Name]"
    carrier_obj = get_carrier(facts.carrier or "")
    airline_name = carrier_obj.name if carrier_obj else (facts.carrier or "[Operating Airline]")
    flight_num = facts.flight_number or "[Flight Number]"
    origin = facts.departure_airport or "[Origin]"
    destination = facts.arrival_airport or "[Destination]"

    if not assessment.applies:
        return (
            f"To: {airline_name} Customer Relations\n"
            f"From: {passenger}\n"
            f"Subject: Ineligibility Notice — Flight {flight_num}\n\n"
            f"Regarding flight {flight_num} from {origin} to {destination}:\n"
            f"Regulation (EC) No 261/2004 does not apply to this flight. "
            f"Reason: {assessment.not_applicable_reason}\n\n"
            f"Sincerely,\n{passenger}\n"
        )

    expected_comp = assessment.compensation.amount_eur if assessment.compensation else None
    narrative = _generate_narrative(facts, expected_comp)

    sections: list[str] = [
        f"To: {airline_name} Customer Relations",
        f"From: {passenger}",
        f"Subject: Compensation Claim under Regulation (EC) No 261/2004 — Flight {flight_num}",
        "",
        f"Dear {airline_name} Claims Team,",
        "",
        narrative,
        "",
        "Flight and Disruption Details:",
        f"- Flight Number: {flight_num}",
        f"- Route: {origin} -> {destination}",
    ]

    comp = assessment.compensation
    if comp and comp.calculation:
        calc = comp.calculation
        sections.append(f"- Great-Circle Distance: {calc.distance_km} km")
        sections.append(f"- Legal Basis: {calc.article}")
        if calc.notes:
            sections.append(f"- Disruption Notes: {calc.notes}")
        if calc.reduction_applied:
            sections.append("- 50% Reduction Applied: Yes (Article 7(2))")

        status_marker = ""
        if comp.status != "verified":
            status_marker = " (not verified against an official source)"
        sections.append(f"\nClaimed Compensation: EUR {comp.amount_eur}{status_marker}")

        if comp.disputed:
            sections.append(
                "\nDispute Notice:\n"
                "The airline may cite extraordinary circumstances for this disruption. "
                "However, under Regulation (EC) No 261/2004, the operating carrier bears the burden of proof "
                "to demonstrate that extraordinary circumstances occurred and could not have been avoided "
                "even if all reasonable measures had been taken. Please provide full documentary proof "
                "if asserting extraordinary circumstances."
            )

        if comp.evidence:
            sections.append("\nOfficial Sources & Evidence:")
            for ev in comp.evidence:
                sections.append(f"- {ev.title or ev.url} ({ev.url})")

    if assessment.care:
        sections.append("\nRight to Care (Article 9):")
        for care_item in assessment.care:
            sections.append(f"- Meals, refreshments and communication facilities owed under Article 9.")

    if assessment.refund_or_rerouting:
        sections.append("\nRight to Reimbursement or Re-routing (Article 8):")
        sections.append("- Full reimbursement or alternative transport owed under Article 8.")

    sections.extend([
        "",
        "Please confirm receipt of this claim and arrange payment within 14 days.",
        "",
        "Sincerely,",
        passenger,
    ])

    return "\n".join(sections) + "\n"


def render_complaint(assessment: Assessment, facts: FlightFacts) -> str:
    """Render a complaint letter to the appropriate National Enforcement Body."""
    passenger = facts.passenger_name or "[Passenger Name]"
    flight_num = facts.flight_number or "[Flight Number]"
    origin = facts.departure_airport or "[Origin]"
    destination = facts.arrival_airport or "[Destination]"
    carrier_obj = get_carrier(facts.carrier or "")
    airline_name = carrier_obj.name if carrier_obj else (facts.carrier or "[Operating Airline]")

    dep_airport = get_airport(facts.departure_airport or "")
    dep_country = dep_airport.country if dep_airport else "PL"

    # Default to departure country NEB, fallback to arrival country if outside EU departure
    if dep_country not in NEB_BODIES and facts.arrival_airport:
        arr_airport = get_airport(facts.arrival_airport)
        if arr_airport and arr_airport.country in NEB_BODIES:
            dep_country = arr_airport.country

    neb_name = NEB_BODIES.get(dep_country, f"National Enforcement Body ({dep_country})")

    sections: list[str] = [
        f"To: {neb_name}",
        f"From: {passenger}",
        f"Subject: Formal Passenger Complaint under Regulation (EC) No 261/2004 — Flight {flight_num}",
        "",
        f"Dear {neb_name},",
        "",
        "Prior Contact with Operating Carrier:",
        "Please note that the operating airline must be contacted first before submitting this complaint. "
        f"A formal claim was previously submitted to {airline_name}, but the airline has failed to settle "
        "or respond adequately in accordance with passenger rights.",
        "",
        "Disruption Summary:",
        f"- Passenger: {passenger}",
        f"- Operating Carrier: {airline_name}",
        f"- Flight: {flight_num}",
        f"- Routing: {origin} -> {destination}",
        f"- Disruption Type: {facts.disruption_type or 'disruption'}",
        f"- Stated Reason: {facts.stated_reason or 'None provided'}",
    ]

    comp = assessment.compensation
    if comp and comp.calculation:
        sections.append(f"- Distance: {comp.calculation.distance_km} km")
        sections.append(f"- Compensation Owed: EUR {comp.amount_eur}")
        sections.append(f"- Applicable Legal Basis: {comp.calculation.article}")

    sections.extend([
        "",
        "I hereby request that the National Enforcement Body investigate this matter and enforce compliance "
        "with Regulation (EC) No 261/2004.",
        "",
        "Sincerely,",
        passenger,
    ])

    return "\n".join(sections) + "\n"
