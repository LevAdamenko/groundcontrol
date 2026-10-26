"""EU261 rules, calculations, and legal eligibility logic."""
from __future__ import annotations

import math
from groundcontrol.airports import EU261_AREA, get_airport
from groundcontrol.carriers import get_carrier
from groundcontrol.models import Assessment, Calculation, Entitlement, FlightFacts


def great_circle_km(iata_a: str, iata_b: str) -> int:
    """Calculate great-circle distance between two airports using Haversine formula (R=6371.0km, floored)."""
    a = get_airport(iata_a)
    b = get_airport(iata_b)
    if not a or not b:
        raise ValueError(f"Unknown airport IATA code: {iata_a!r} or {iata_b!r}")
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (math.sin(dlat / 2.0) ** 2) + math.cos(lat1) * math.cos(lat2) * (math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(h), math.sqrt(1.0 - h))
    return math.floor(6371.0 * c)


def compensation_band(distance_km: int, intra_area: bool) -> int:
    """Return EU261 Article 7(1) base compensation band (250, 400, or 600 EUR)."""
    if distance_km <= 1500:
        return 250
    if intra_area:
        return 400
    if distance_km <= 3500:
        return 400
    return 600


def delay_compensation(distance_km: int, intra_area: bool, arrival_delay_min: int) -> int:
    """Calculate compensation for delay under Article 6 and CJEU Sturgeon jurisprudence."""
    if arrival_delay_min < 180:
        return 0
    band = compensation_band(distance_km, intra_area)
    # For the 600 EUR band, arrival delay 180-239 min is reduced by 50% to 300 EUR (Art. 7(2)(c))
    if band == 600 and arrival_delay_min < 240:
        return 300
    return band


def cancellation_compensation(
    distance_km: int,
    intra_area: bool,
    notice_days: int,
    reroute_departs_early_min: int | None = None,
    reroute_arrives_late_min: int | None = None,
) -> int:
    """Calculate compensation for cancellation under Article 5(1)(c) and Article 7(2)."""
    # 14 days or more before scheduled departure: no compensation
    if notice_days >= 14:
        return 0

    # 7-13 days before scheduled departure
    if 7 <= notice_days <= 13:
        if (
            reroute_departs_early_min is not None
            and reroute_arrives_late_min is not None
            and reroute_departs_early_min <= 120
            and reroute_arrives_late_min < 240
        ):
            return 0

    # Less than 7 days before scheduled departure
    if notice_days < 7:
        if (
            reroute_departs_early_min is not None
            and reroute_arrives_late_min is not None
            and reroute_departs_early_min <= 60
            and reroute_arrives_late_min < 120
        ):
            return 0

    band = compensation_band(distance_km, intra_area)

    # 50% reduction under Article 7(2) when rerouting is accepted
    if reroute_arrives_late_min is not None:
        reduction_threshold = 120 if band == 250 else (180 if band == 400 else 240)
        if reroute_arrives_late_min <= reduction_threshold:
            return band // 2

    return band


def applies(facts: FlightFacts) -> tuple[bool, str | None]:
    """Check EU261 territorial and carrier scope under Article 3(1)."""
    dep_code = facts.departure_airport
    arr_code = facts.arrival_airport

    if not dep_code or not arr_code:
        return False, "Missing departure or arrival airport."

    dep = get_airport(dep_code)
    arr = get_airport(arr_code)

    if not dep or not arr:
        return False, f"Unknown airport code: {dep_code if not dep else arr_code}."

    # Condition 1: Flight departs from an airport in the EU261 area
    if dep.in_eu261_area:
        return True, None

    # Condition 2: Flight departs outside area, arrives inside, operated by EU261 carrier
    carrier = get_carrier(facts.carrier or "")
    if arr.in_eu261_area:
        if carrier and carrier.is_eu261:
            return True, None
        reason = "EU261 does not apply: flight departs outside the EU261 area and the operating carrier is not an EU261 carrier."
        if dep.country == "GB":
            reason += " The UK's own regulation (UK261) may apply instead; it is outside GroundControl's scope."
        return False, reason

    return False, "EU261 does not apply: flight neither departs from nor arrives in the EU261 area."


def classify_reason(text: str | None) -> tuple[bool, str]:
    """Classify disruption reason into disputed (extraordinary circumstances) and case reference."""
    if not text:
        return False, "No extraordinary circumstances established."

    lower = text.lower()

    # Extraordinary circumstances under Art. 5(3) & Recital 14
    extraordinary_keywords = [
        "weather", "thunderstorm", "fog", "snow", "blizzard", "storm",
        "air traffic control", "atc restriction", "airport strike",
        "security", "political instability", "bird strike",
    ]
    if any(k in lower for k in extraordinary_keywords):
        return (
            True,
            "Disruption may involve extraordinary circumstances (Article 5(3), Recital 14). "
            "The operating air carrier bears the burden of proving that the disruption was caused by "
            "extraordinary circumstances that could not have been avoided even if all reasonable measures had been taken.",
        )

    # Technical faults: NOT extraordinary (CJEU C-549/07 Wallentin-Hermann)
    if any(k in lower for k in ["technical", "mechanical", "fault", "defect", "aircraft maintenance"]):
        return (
            False,
            "Technical faults are inherent in the normal exercise of the activity of the air carrier "
            "and do not constitute extraordinary circumstances (CJEU Case C-549/07 Wallentin-Hermann).",
        )

    # Airline staff strikes: NOT extraordinary (CJEU C-28/20)
    if any(k in lower for k in ["airline staff strike", "pilot strike", "cabin crew strike", "internal strike"]):
        return (
            False,
            "Strikes organized by airline staff to assert employment demands are inherent in normal business operations "
            "and do not constitute extraordinary circumstances (CJEU Case C-28/20).",
        )

    # Crew shortage / operational reasons: NOT extraordinary
    if any(k in lower for k in ["crew shortage", "operational", "sickness", "crew delay", "staff shortage"]):
        return (
            False,
            "Crew shortages and operational planning difficulties are inherent in the normal operation "
            "of an air carrier and do not constitute extraordinary circumstances.",
        )

    return False, "Standard disruption; no extraordinary circumstances established."


def assess(facts: FlightFacts) -> Assessment:
    """Assess passenger entitlements under EU261."""
    missing: list[str] = []
    if not facts.departure_airport:
        missing.append("departure_airport")
    if not facts.arrival_airport:
        missing.append("arrival_airport")
    if not facts.carrier:
        missing.append("carrier")
    if not facts.flight_number:
        missing.append("flight_number")
    if not facts.disruption_type:
        missing.append("disruption_type")
    if facts.disruption_type == "delay" and facts.arrival_delay_min is None:
        missing.append("arrival_delay_min")
    if facts.disruption_type == "cancellation" and facts.notice_days is None:
        missing.append("notice_days")

    applicable, not_applicable_reason = applies(facts)

    distance_km: int | None = None
    intra_area = False
    if facts.departure_airport and facts.arrival_airport:
        try:
            distance_km = great_circle_km(facts.departure_airport, facts.arrival_airport)
            dep = get_airport(facts.departure_airport)
            arr = get_airport(facts.arrival_airport)
            if dep and arr:
                intra_area = dep.in_eu261_area and arr.in_eu261_area
        except Exception:
            pass

    if not applicable:
        return Assessment(
            applies=False,
            not_applicable_reason=not_applicable_reason,
            compensation=None,
            care=[],
            refund_or_rerouting=None,
            missing_facts=missing,
            intra_area=intra_area,
            distance_km=distance_km,
        )

    assert distance_km is not None
    band_eur = compensation_band(distance_km, intra_area)
    disputed, disputed_reason = classify_reason(facts.stated_reason)

    compensation: Entitlement | None = None
    care_list: list[Entitlement] = []
    refund_or_rerouting: Entitlement | None = None

    if facts.disruption_type == "cancellation":
        comp_amount = cancellation_compensation(
            distance_km=distance_km,
            intra_area=intra_area,
            notice_days=facts.notice_days or 0,
            reroute_departs_early_min=facts.reroute_departs_early_min,
            reroute_arrives_late_min=facts.reroute_arrives_late_min,
        )
        reduction_applied = (0 < comp_amount < band_eur)
        calc = Calculation(
            distance_km=distance_km,
            arrival_delay_min=facts.reroute_arrives_late_min,
            notice_days=facts.notice_days,
            band_eur=band_eur,
            reduction_applied=reduction_applied,
            article="Article 5(1)(c), Article 7",
            notes=(
                f"Cancellation notified {facts.notice_days} days before departure."
                if facts.notice_days is not None
                else "Notice date not stated; assumed under 7 days. Provisional until confirmed."
            ),
            provisional=facts.notice_days is None,
        )
        compensation = Entitlement(
            kind="compensation",
            amount_eur=comp_amount,
            calculation=calc,
            evidence=[],
            disputed=disputed,
            disputed_reason=disputed_reason,
            article="Article 7",
        )

        # Care is always owed for cancellations (Art. 5(1)(b), Art. 9)
        care_calc = Calculation(distance_km=distance_km, article="Article 9", notes="Right to care for cancelled flight")
        care_list.append(
            Entitlement(
                kind="care",
                amount_eur=0,
                calculation=care_calc,
                evidence=[],
                disputed=False,
                article="Article 9",
            )
        )

        # Reimbursement or re-routing is always owed for cancellations (Art. 5(1)(a), Art. 8)
        refund_calc = Calculation(distance_km=distance_km, article="Article 8", notes="Right to reimbursement or re-routing")
        refund_or_rerouting = Entitlement(
            kind="refund_or_rerouting",
            amount_eur=0,
            calculation=refund_calc,
            evidence=[],
            disputed=False,
            article="Article 8",
        )

    elif facts.disruption_type == "delay":
        delay_min = facts.arrival_delay_min or 0
        comp_amount = delay_compensation(
            distance_km=distance_km,
            intra_area=intra_area,
            arrival_delay_min=delay_min,
        )
        reduction_applied = (0 < comp_amount < band_eur)
        calc = Calculation(
            distance_km=distance_km,
            arrival_delay_min=delay_min,
            band_eur=band_eur,
            reduction_applied=reduction_applied,
            article="Article 6, CJEU C-402/07 Sturgeon, Article 7",
            notes=f"Arrival delay of {delay_min} minutes.",
        )
        compensation = Entitlement(
            kind="compensation",
            amount_eur=comp_amount,
            calculation=calc,
            evidence=[],
            disputed=disputed,
            disputed_reason=disputed_reason,
            article="Article 7",
        )

        dep_delay = facts.departure_delay_min if facts.departure_delay_min is not None else delay_min
        care_threshold = 120 if band_eur == 250 else (180 if band_eur == 400 else 240)
        if dep_delay >= care_threshold:
            care_calc = Calculation(distance_km=distance_km, arrival_delay_min=dep_delay, article="Article 9", notes="Right to care during delay")
            care_list.append(
                Entitlement(
                    kind="care",
                    amount_eur=0,
                    calculation=care_calc,
                    evidence=[],
                    disputed=False,
                    article="Article 9",
                )
            )

        if dep_delay >= 300:
            ref_calc = Calculation(distance_km=distance_km, arrival_delay_min=dep_delay, article="Article 8", notes="Right to reimbursement for delay >= 5 hours")
            refund_or_rerouting = Entitlement(
                kind="refund_or_rerouting",
                amount_eur=0,
                calculation=ref_calc,
                evidence=[],
                disputed=False,
                article="Article 8",
            )

    return Assessment(
        applies=True,
        not_applicable_reason=None,
        compensation=compensation,
        care=care_list,
        refund_or_rerouting=refund_or_rerouting,
        missing_facts=missing,
        intra_area=intra_area,
        distance_km=distance_km,
    )
