"""Carriers (fictional airlines for synthetic data)."""
from __future__ import annotations

from dataclasses import dataclass
from groundcontrol.airports import EU261_AREA


@dataclass(frozen=True)
class Carrier:
    code: str
    name: str
    country: str

    @property
    def is_eu261(self) -> bool:
        return self.country in EU261_AREA


CARRIERS: dict[str, Carrier] = {
    "VQ": Carrier("VQ", "Vistula Air", "PL"),
    "GH": Carrier("GH", "Gulf Horizon", "AE"),
}


def get_carrier(identifier: str) -> Carrier | None:
    if not identifier:
        return None
    ident = identifier.strip().upper()
    if ident in CARRIERS:
        return CARRIERS[ident]
    for c in CARRIERS.values():
        if c.name.upper() == ident or c.code == ident:
            return c
    return None
