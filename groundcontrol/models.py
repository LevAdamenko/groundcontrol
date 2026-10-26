"""Core data models for GroundControl."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class FlightFacts:
    flight_number: str | None = None
    carrier: str | None = None
    departure_airport: str | None = None
    arrival_airport: str | None = None
    scheduled_departure: str | None = None
    scheduled_arrival: str | None = None
    actual_arrival: str | None = None
    disruption_type: str | None = None  # "delay" or "cancellation"
    stated_reason: str | None = None
    notice_days: int | None = None
    reroute_departs_early_min: int | None = None
    reroute_arrives_late_min: int | None = None
    departure_delay_min: int | None = None
    arrival_delay_min: int | None = None
    passenger_name: str | None = None


@dataclass
class Calculation:
    distance_km: int
    arrival_delay_min: int | None = None
    notice_days: int | None = None
    band_eur: int = 0
    reduction_applied: bool = False
    article: str = ""
    notes: str = ""
    provisional: bool = False  # an input was assumed, not stated: never "verified"


@dataclass
class Evidence:
    url: str
    title: str
    snippet: str
    anchor: str


@dataclass
class Entitlement:
    kind: str
    amount_eur: int = 0
    calculation: Calculation | None = None
    evidence: list[Evidence] = field(default_factory=list)
    disputed: bool = False
    disputed_reason: str | None = None
    article: str = ""
    required_anchors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.calculation is None:
            return "unverified"
        if self.calculation.provisional or not self.evidence:
            return "unverified"
        from groundcontrol.verify import ALLOWED_DOMAINS

        def _backed(anchor: str) -> bool:
            for ev in self.evidence:
                if not (ev.anchor == anchor and anchor and anchor in ev.snippet):
                    continue
                try:
                    host = urlparse(ev.url).netloc.split(":")[0].lower()
                except Exception:
                    continue
                if any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS):
                    return True
            return False

        # Every required anchor needs its own official source; with none declared,
        # any anchored allow-listed source is enough.
        if self.required_anchors:
            backed = all(_backed(a) for a in self.required_anchors)
        else:
            backed = any(_backed(ev.anchor) for ev in self.evidence)
        if backed:
            return "verified"
        return "unverified"


@dataclass
class Assessment:
    applies: bool
    not_applicable_reason: str | None = None
    compensation: Entitlement | None = None
    care: list[Entitlement] = field(default_factory=list)
    refund_or_rerouting: Entitlement | None = None
    missing_facts: list[str] = field(default_factory=list)
    intra_area: bool = False
    distance_km: int | None = None
    verification_error: str | None = None
