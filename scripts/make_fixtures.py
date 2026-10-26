"""Deterministic generator for GroundControl test fixtures."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from groundcontrol.clients import get_fixtures_dir, stable_hash
from groundcontrol.config import get_nemotron_model
from groundcontrol.drafts import NARRATIVE_SYSTEM_PROMPT
from groundcontrol.extract import EXTRACTION_SYSTEM_PROMPT
from groundcontrol.models import FlightFacts
from groundcontrol.verify import ALLOWED_DOMAINS

FIXTURES_DIR = get_fixtures_dir()
SCENARIOS_DIR = FIXTURES_DIR / "scenarios"
NEMOTRON_DIR = FIXTURES_DIR / "nemotron"
TAVILY_DIR = FIXTURES_DIR / "tavily"

GENERATED_NEMOTRON_HASHES: set[str] = set()
GENERATED_TAVILY_HASHES: set[str] = set()

SCENARIOS = {
    "cancel-short-notice": {
        "id": "cancel-short-notice",
        "title": "WAW to LIS cancellation with 5 days notice",
        "input_text": (
            "From: notifications@vistula-air.com\n"
            "To: anna.kowalska@example.com\n"
            "Subject: Flight VQ401 Cancellation Notice\n\n"
            "Dear Anna Kowalska,\n\n"
            "We regret to inform you that flight VQ401 scheduled from Warsaw Chopin (WAW) to Lisbon (LIS) "
            "on May 15, 2026, departing at 10:00 and arriving at 13:30, has been cancelled due to operational reorganization.\n\n"
            "Notice of cancellation is provided 5 days prior to scheduled departure. No alternative rerouting is available at this time. "
            "Under applicable regulations, you are entitled to reimbursement or rerouting, as well as assistance.\n\n"
            "Vistula Air Customer Service"
        ),
        "facts": {
            "flight_number": "VQ401",
            "carrier": "VQ",
            "departure_airport": "WAW",
            "arrival_airport": "LIS",
            "scheduled_departure": "2026-05-15T10:00:00",
            "scheduled_arrival": "2026-05-15T13:30:00",
            "actual_arrival": None,
            "disruption_type": "cancellation",
            "stated_reason": "Operational reorganization",
            "notice_days": 5,
            "reroute_departs_early_min": None,
            "reroute_arrives_late_min": None,
            "departure_delay_min": None,
            "arrival_delay_min": None,
            "passenger_name": "Anna Kowalska",
        },
        "expected": {
            "applies": True,
            "amount": 400,
            "disputed": False,
        },
        "narrative": (
            "I was booked on flight VQ401 from Warsaw (WAW) to Lisbon (LIS) on May 15, 2026. "
            "Five days prior to departure, Vistula Air notified me that the flight was cancelled due to "
            "operational reorganization, without providing suitable alternative rerouting."
        ),
    },
    "delay-3h40": {
        "id": "delay-3h40",
        "title": "WAW to CDG delay 3h40 due to technical fault",
        "input_text": (
            "I am writing to file a compensation claim for flight VQ202 operated by Vistula Air "
            "from Warsaw (WAW) to Paris Charles de Gaulle (CDG) on June 10, 2026.\n"
            "My name is Jan Nowak. We were scheduled to depart WAW at 14:00 and arrive in CDG at 16:30. "
            "Due to a technical fault with the aircraft hydraulic system discovered before takeoff, "
            "our flight was severely delayed. We did not arrive at Paris CDG until 20:10, which is an arrival delay "
            "of 3 hours and 40 minutes (220 minutes)."
        ),
        "facts": {
            "flight_number": "VQ202",
            "carrier": "VQ",
            "departure_airport": "WAW",
            "arrival_airport": "CDG",
            "scheduled_departure": "2026-06-10T14:00:00",
            "scheduled_arrival": "2026-06-10T16:30:00",
            "actual_arrival": "2026-06-10T20:10:00",
            "disruption_type": "delay",
            "stated_reason": "Technical fault with aircraft hydraulic system",
            "notice_days": None,
            "reroute_departs_early_min": None,
            "reroute_arrives_late_min": None,
            "departure_delay_min": 220,
            "arrival_delay_min": 220,
            "passenger_name": "Jan Nowak",
        },
        "expected": {
            "applies": True,
            "amount": 250,
            "disputed": False,
        },
        "narrative": (
            "I was a passenger on flight VQ202 scheduled from Warsaw (WAW) to Paris (CDG) on June 10, 2026. "
            "The flight suffered a technical hydraulic fault, causing an arrival delay of 3 hours and 40 minutes in Paris."
        ),
    },
    "delay-weather": {
        "id": "delay-weather",
        "title": "WAW to JFK delay 5h due to thunderstorm",
        "input_text": (
            "Dear Vistula Air Team,\n\n"
            "I am writing regarding flight VQ505 from Warsaw (WAW) to New York (JFK) on July 20, 2026. "
            "Passenger name: Piotr Wiśniewski.\n"
            "Scheduled departure was 11:00 with scheduled arrival at JFK at 14:45. However, our arrival was "
            "delayed by 5 hours (300 minutes), finally arriving at 19:45. The captain stated the delay was "
            "caused by severe thunderstorm and lightning along the transatlantic flight route."
        ),
        "facts": {
            "flight_number": "VQ505",
            "carrier": "VQ",
            "departure_airport": "WAW",
            "arrival_airport": "JFK",
            "scheduled_departure": "2026-07-20T11:00:00",
            "scheduled_arrival": "2026-07-20T14:45:00",
            "actual_arrival": "2026-07-20T19:45:00",
            "disruption_type": "delay",
            "stated_reason": "Severe thunderstorm and lightning along the transatlantic flight route",
            "notice_days": None,
            "reroute_departs_early_min": None,
            "reroute_arrives_late_min": None,
            "departure_delay_min": 300,
            "arrival_delay_min": 300,
            "passenger_name": "Piotr Wiśniewski",
        },
        "expected": {
            "applies": True,
            "amount": 600,
            "disputed": True,
        },
        "narrative": (
            "On July 20, 2026, I travelled on flight VQ505 from Warsaw (WAW) to New York (JFK). "
            "The flight arrived 5 hours behind schedule, with the airline attributing the disruption to severe thunderstorm conditions."
        ),
    },
    "longhaul-3h30": {
        "id": "longhaul-3h30",
        "title": "WAW to JFK delay 3h30 due to crew shortage",
        "input_text": (
            "BOARDING PASS DUMP:\n"
            "PASSENGER: KATARZYNA WOJCIK\n"
            "FLIGHT: VQ507 / OPERATED BY: VISTULA AIR\n"
            "DATE: 05AUG2026\n"
            "FROM: WAW (WARSAW CHOPIN)\n"
            "TO: JFK (NEW YORK JOHN F KENNEDY)\n"
            "STD: 12:00 / STA: 15:30\n"
            "ACTUAL ARRIVAL: 19:00 (ATA)\n"
            "DISRUPTION: DELAY (ARRIVAL DELAY 210 MIN / 3 HOURS 30 MINUTES)\n"
            "REASON: CREW SHORTAGE DUE TO ROSTERING MISTAKE\n"
            "NOTE: Seeking compensation for long-haul arrival delay."
        ),
        "facts": {
            "flight_number": "VQ507",
            "carrier": "VQ",
            "departure_airport": "WAW",
            "arrival_airport": "JFK",
            "scheduled_departure": "2026-08-05T12:00:00",
            "scheduled_arrival": "2026-08-05T15:30:00",
            "actual_arrival": "2026-08-05T19:00:00",
            "disruption_type": "delay",
            "stated_reason": "Crew shortage due to rostering mistake",
            "notice_days": None,
            "reroute_departs_early_min": None,
            "reroute_arrives_late_min": None,
            "departure_delay_min": 210,
            "arrival_delay_min": 210,
            "passenger_name": "Katarzyna Wójcik",
        },
        "expected": {
            "applies": True,
            "amount": 300,
            "disputed": False,
        },
        "narrative": (
            "On August 5, 2026, my flight VQ507 from Warsaw (WAW) to New York (JFK) was delayed upon arrival "
            "by 3 hours and 30 minutes due to crew shortage and scheduling problems."
        ),
    },
    "outside-scope": {
        "id": "outside-scope",
        "title": "DXB to WAW on Gulf Horizon delay 6h outside EU261 scope",
        "input_text": (
            "Customer Claim Enquiry:\n"
            "Passenger Name: Marek Zieliński\n"
            "Flight GH901 from Dubai (DXB) to Warsaw (WAW), operated by Gulf Horizon on September 12, 2026.\n"
            "Scheduled departure: 08:00, scheduled arrival: 12:30.\n"
            "Actual arrival in Warsaw: 18:30 (6 hours / 360 minutes late).\n"
            "Disruption: Long delay. Reason given by carrier: Aircraft turnaround delay in Dubai.\n"
            "Does EU261 compensation apply to this flight?"
        ),
        "facts": {
            "flight_number": "GH901",
            "carrier": "GH",
            "departure_airport": "DXB",
            "arrival_airport": "WAW",
            "scheduled_departure": "2026-09-12T08:00:00",
            "scheduled_arrival": "2026-09-12T12:30:00",
            "actual_arrival": "2026-09-12T18:30:00",
            "disruption_type": "delay",
            "stated_reason": "Aircraft turnaround delay in Dubai",
            "notice_days": None,
            "reroute_departs_early_min": None,
            "reroute_arrives_late_min": None,
            "departure_delay_min": 360,
            "arrival_delay_min": 360,
            "passenger_name": "Marek Zieliński",
        },
        "expected": {
            "applies": False,
            "amount": 0,
            "disputed": False,
        },
        "narrative": "",
    },
}

# Real wording of EU261 rules and official sources
TAVILY_CORPUS = {
    "EUR 250": [
        {
            "url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj",
            "title": "Regulation (EC) No 261/2004 - Article 7 Right to compensation",
            "content": (
                "Article 7 Right to compensation. 1. Where reference is made to this Article, "
                "passengers shall receive compensation amounting to: "
                "(a) EUR 250 for all flights of 1500 kilometres or less; "
                "(b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres; "
                "(c) EUR 600 for all flights not falling under (a) or (b)."
            ),
        },
        {
            "url": "https://europa.eu/youreurope/citizens/travel/passenger-rights/air/index_en.htm",
            "title": "Air passenger rights - Your Europe",
            "content": (
                "Under EU rules, if your flight arrives at your final destination 3 hours or more after schedule, "
                "you are entitled to compensation: EUR 250 for flights up to 1500 km."
            ),
        },
        {
            "url": "https://flight-claims-blog.example.com/eu261",
            "title": "Passenger Rights Blog - Non-official claim guide",
            "content": "Get your EUR 250 compensation quickly through our agency blog.",
        },
    ],
    "EUR 400": [
        {
            "url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj",
            "title": "Regulation (EC) No 261/2004 - Article 7 Right to compensation",
            "content": (
                "Article 7 Right to compensation. 1. Where reference is made to this Article, "
                "passengers shall receive compensation amounting to: "
                "(a) EUR 250 for all flights of 1500 kilometres or less; "
                "(b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres; "
                "(c) EUR 600 for all flights not falling under (a) or (b)."
            ),
        },
        {
            "url": "https://ulc.gov.pl/en/passenger-rights/passenger-rights-under-ec-regulation-261-2004",
            "title": "Civil Aviation Authority (ULC) Poland - Passenger Rights",
            "content": (
                "Compensation under Regulation 261/2004: EUR 400 for all intra-Community flights of more than 1500 kilometres, "
                "and for all other flights between 1500 and 3500 kilometres."
            ),
        },
        {
            "url": "https://air-claims-unverified.example.com/compensation",
            "title": "Unverified Claims Portal",
            "content": "Claim up to EUR 400 now with our automated submission tool.",
        },
    ],
    "EUR 600": [
        {
            "url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj",
            "title": "Regulation (EC) No 261/2004 - Article 7 Right to compensation",
            "content": (
                "Article 7 Right to compensation. 1. Where reference is made to this Article, "
                "passengers shall receive compensation amounting to: "
                "(a) EUR 250 for all flights of 1500 kilometres or less; "
                "(b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres; "
                "(c) EUR 600 for all flights not falling under (a) or (b)."
            ),
        },
        {
            "url": "https://transport.ec.europa.eu/transport-modes/air/passenger-rights_en",
            "title": "European Commission - Air Passenger Rights Overview",
            "content": (
                "For flights not falling under (a) or (b) exceeding 3500 kilometres, compensation of EUR 600 is owed "
                "when passengers reach their final destination three hours or more after the scheduled arrival time."
            ),
        },
        {
            "url": "https://flight-claims-blog.example.com/eu261",
            "title": "Passenger Rights Blog - Non-official claim guide",
            "content": "Long haul flight delay compensation can reach EUR 600.",
        },
    ],
    "three hours or more": [
        {
            "url": "https://curia.europa.eu/juris/document/document.jsf?docid=73703",
            "title": "CJEU Judgment in Joined Cases C-402/07 and C-432/07 Sturgeon and Others",
            "content": (
                "Articles 5, 6 and 7 of Regulation (EC) No 261/2004 must be interpreted as meaning that passengers whose flights "
                "are delayed may be treated, for the purposes of the application of the right to compensation, as passengers whose "
                "flights are cancelled and they may thus rely on the right to compensation laid down in Article 7 of the regulation "
                "where they suffer, on account of a flight delay, a loss of time equal to or in excess of three hours or more."
            ),
        },
        {
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62007CJ0402",
            "title": "EUR-Lex - Case C-402/07 Sturgeon",
            "content": (
                "Judgment of the Court (Fourth Chamber) of 19 November 2009. Sturgeon. A loss of time equal to or in excess "
                "of three hours or more entitles passengers to Article 7 compensation."
            ),
        },
    ],
    "meals and refreshments": [
        {
            "url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj",
            "title": "Regulation (EC) No 261/2004 - Article 9 Right to care",
            "content": (
                "Article 9 Right to care. 1. Where reference is made to this Article, passengers shall be offered free of charge: "
                "(a) meals and refreshments in a reasonable relation to the waiting time; "
                "(b) hotel accommodation in cases where a stay of one or more nights becomes necessary; "
                "(c) transport between the airport and place of accommodation."
            ),
        },
        {
            "url": "https://europa.eu/youreurope/citizens/travel/passenger-rights/air/index_en.htm",
            "title": "Air passenger rights - Your Europe",
            "content": (
                "Airlines must provide free care including meals and refreshments and free communication (phone calls or emails) "
                "while you wait for your delayed or rerouted flight."
            ),
        },
    ],
    "reimbursement": [
        {
            "url": "https://eur-lex.europa.eu/eli/reg/2004/261/oj",
            "title": "Regulation (EC) No 261/2004 - Article 8 Right to reimbursement or re-routing",
            "content": (
                "Article 8 Right to reimbursement or re-routing. 1. Where reference is made to this Article, passengers shall be "
                "offered the choice between: (a) reimbursement within seven days of the full cost of the ticket at the price "
                "at which it was bought; (b) re-routing, under comparable transport conditions, to their final destination."
            ),
        },
        {
            "url": "https://transport.ec.europa.eu/transport-modes/air/passenger-rights_en",
            "title": "European Commission - Air Passenger Rights Overview",
            "content": (
                "In case of flight cancellation or delay of five hours or more, passengers are entitled to reimbursement "
                "of the ticket cost within seven days."
            ),
        },
    ],
}


def write_fixture(dir_path: Path, req_hash: str, payload: dict, response: object) -> None:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    fixture_file = dir_path / f"{req_hash}.json"
    data = {
        "request": payload,
        "response": response,
        "recorded": False,
    }
    if fixture_file.is_file():
        try:
            if json.loads(fixture_file.read_text(encoding="utf-8")) == data:
                print(f"Fixture already up to date: {fixture_file.relative_to(ROOT)} (hash: {req_hash})")
                return
        except Exception:
            pass
    try:
        fixture_file.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote fixture: {fixture_file.relative_to(ROOT)} (hash: {req_hash})")
    except PermissionError:
        print(f"Fixture already exists (read-only): {fixture_file.relative_to(ROOT)} (hash: {req_hash})")


RETRY_TEST_INPUT = (
    "Flight VQ999 operated by Vistula Air from Warsaw (WAW) to Paris (CDG) on 2026-06-15 was delayed by 200 minutes due to hydraulic issues. Passenger: Maria Kowalczyk."
)
RETRY_FACTS = {
    "flight_number": "VQ999",
    "carrier": "VQ",
    "departure_airport": "WAW",
    "arrival_airport": "CDG",
    "scheduled_departure": "2026-06-15T10:00:00",
    "scheduled_arrival": "2026-06-15T12:30:00",
    "actual_arrival": "2026-06-15T15:50:00",
    "disruption_type": "delay",
    "stated_reason": "hydraulic issues",
    "notice_days": None,
    "reroute_departs_early_min": None,
    "reroute_arrives_late_min": None,
    "departure_delay_min": 200,
    "arrival_delay_min": 200,
    "passenger_name": "Maria Kowalczyk",
}

DOUBLE_INVALID_INPUT = (
    "Flight VQ888 from Warsaw (WAW) to Berlin (BER) was cancelled on short notice. Passenger: Piotr Zielinski."
)


def make_nemotron_fixture(messages: list[dict], response: object, response_format: dict | None = None) -> str:
    model = get_nemotron_model()
    payload = {"messages": messages, "model": model}
    if response_format is not None:
        payload["response_format"] = response_format
    h = stable_hash(payload)
    GENERATED_NEMOTRON_HASHES.add(h)
    write_fixture(NEMOTRON_DIR, h, payload, response)
    return h


def make_tavily_fixture(query: str, include_domains: list[str] | tuple[str, ...], results: list[dict]) -> str:
    domains = sorted(list(include_domains)) if include_domains else []
    payload = {
        "include_domains": domains,
        "max_results": 5,
        "query": query,
    }
    h = stable_hash(payload)
    GENERATED_TAVILY_HASHES.add(h)
    write_fixture(TAVILY_DIR, h, payload, {"results": results})
    return h


def main() -> None:
    try:
        SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
        NEMOTRON_DIR.mkdir(parents=True, exist_ok=True)
        TAVILY_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    # 1. Write scenario JSON files
    for sid, sdata in SCENARIOS.items():
        scen_file = SCENARIOS_DIR / f"{sid}.json"
        scenario_content = {
            "id": sdata["id"],
            "title": sdata["title"],
            "input_text": sdata["input_text"],
            "expected": sdata["expected"],
        }
        if scen_file.is_file():
            try:
                if json.loads(scen_file.read_text(encoding="utf-8")) == scenario_content:
                    print(f"Scenario already up to date: {scen_file.relative_to(ROOT)}")
            except Exception:
                pass
        else:
            try:
                scen_file.write_text(json.dumps(scenario_content, indent=2), encoding="utf-8")
                print(f"Wrote scenario: {scen_file.relative_to(ROOT)}")
            except PermissionError:
                print(f"Scenario already exists (read-only): {scen_file.relative_to(ROOT)}")

        # 2. Extraction Nemotron fixture for this scenario
        extract_messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": sdata["input_text"]},
        ]
        make_nemotron_fixture(
            extract_messages,
            json.dumps(sdata["facts"]),
            response_format={"type": "json_object"},
        )

        # 3. Narrative Nemotron fixture (if applicable)
        facts = FlightFacts(**sdata["facts"])
        if sdata["expected"]["applies"]:
            narrative_messages = [
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
                        f"Delay / notice: {facts.arrival_delay_min if facts.arrival_delay_min is not None else facts.notice_days}."
                    ),
                },
            ]
            make_nemotron_fixture(narrative_messages, sdata["narrative"])

    # 4. Tavily search fixtures for all queries used in verify.py
    # Compensation queries
    for amount in (250, 400, 600):
        q = f"Regulation 261 2004 EUR {amount} Article 7"
        make_tavily_fixture(q, list(ALLOWED_DOMAINS), TAVILY_CORPUS[f"EUR {amount}"])

    # CJEU Sturgeon query for 300 EUR case
    q_sturgeon = "CJEU Sturgeon C-402/07 three hours or more"
    make_tavily_fixture(q_sturgeon, ["curia.europa.eu", "eur-lex.europa.eu"], TAVILY_CORPUS["three hours or more"])

    # Care query
    q_care = "Regulation 261 2004 meals and refreshments Article 9"
    make_tavily_fixture(q_care, list(ALLOWED_DOMAINS), TAVILY_CORPUS["meals and refreshments"])

    # Refund query
    q_refund = "Regulation 261 2004 reimbursement Article 8"
    make_tavily_fixture(q_refund, list(ALLOWED_DOMAINS), TAVILY_CORPUS["reimbursement"])

    # 5. Retry path fixture pair for offline tests
    retry_msg_1 = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": RETRY_TEST_INPUT},
    ]
    retry_resp_1 = "Sorry, I cannot process this disruption into JSON."
    make_nemotron_fixture(retry_msg_1, retry_resp_1, response_format={"type": "json_object"})

    retry_msg_2 = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": RETRY_TEST_INPUT},
        {"role": "assistant", "content": retry_resp_1},
        {"role": "user", "content": "Your previous reply was not a valid JSON object. Reply with only the JSON object."},
    ]
    retry_resp_2 = json.dumps(RETRY_FACTS)
    make_nemotron_fixture(retry_msg_2, retry_resp_2, response_format={"type": "json_object"})

    # 6. Double invalid fixtures for offline tests
    double_msg_1 = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": DOUBLE_INVALID_INPUT},
    ]
    double_resp_1 = "First invalid non-JSON output."
    make_nemotron_fixture(double_msg_1, double_resp_1, response_format={"type": "json_object"})

    double_msg_2 = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": DOUBLE_INVALID_INPUT},
        {"role": "assistant", "content": double_resp_1},
        {"role": "user", "content": "Your previous reply was not a valid JSON object. Reply with only the JSON object."},
    ]
    double_resp_2 = "Second invalid non-JSON output."
    make_nemotron_fixture(double_msg_2, double_resp_2, response_format={"type": "json_object"})

    # 7. Clean up orphan fixture files
    for p in NEMOTRON_DIR.glob("*.json"):
        if p.stem not in GENERATED_NEMOTRON_HASHES:
            print(f"Removing orphan nemotron fixture: {p.name}")
            p.unlink()

    for p in TAVILY_DIR.glob("*.json"):
        if p.stem not in GENERATED_TAVILY_HASHES:
            print(f"Removing orphan tavily fixture: {p.name}")
            p.unlink()

    print("Deterministic fixtures successfully generated.")


if __name__ == "__main__":
    main()
