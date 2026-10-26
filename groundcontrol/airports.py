"""Airports and EU261 geographic scope."""
from __future__ import annotations

from dataclasses import dataclass

EU27_COUNTRIES = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})

# EU261 applies to EU27 + Iceland, Norway, Switzerland
EU261_AREA = frozenset(EU27_COUNTRIES | {"IS", "NO", "CH"})


@dataclass(frozen=True)
class Airport:
    code: str
    name: str
    country: str
    lat: float
    lon: float

    @property
    def in_eu261_area(self) -> bool:
        return self.country in EU261_AREA


AIRPORTS: dict[str, Airport] = {
    "WAW": Airport("WAW", "Warsaw Chopin Airport", "PL", 52.1672, 20.9679),
    "KRK": Airport("KRK", "Kraków John Paul II Airport", "PL", 50.0777, 19.7848),
    "GDN": Airport("GDN", "Gdańsk Lech Wałęsa Airport", "PL", 54.3776, 18.4662),
    "CDG": Airport("CDG", "Paris Charles de Gaulle Airport", "FR", 49.0097, 2.5479),
    "FRA": Airport("FRA", "Frankfurt Airport", "DE", 50.0379, 8.5622),
    "LIS": Airport("LIS", "Lisbon Airport", "PT", 38.7742, -9.1342),
    "BCN": Airport("BCN", "Barcelona-El Prat Airport", "ES", 41.2974, 2.0833),
    "MAD": Airport("MAD", "Madrid-Barajas Airport", "ES", 40.4839, -3.5680),
    "JFK": Airport("JFK", "John F. Kennedy International Airport", "US", 40.6413, -73.7781),
    "DXB": Airport("DXB", "Dubai International Airport", "AE", 25.2532, 55.3657),
    "LHR": Airport("LHR", "London Heathrow Airport", "GB", 51.4700, -0.4543),
    "OSL": Airport("OSL", "Oslo Airport Gardermoen", "NO", 60.1975, 11.1004),
}


def get_airport(code: str) -> Airport | None:
    return AIRPORTS.get(code.upper().strip())
