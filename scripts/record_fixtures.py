"""Record live fixtures for GroundControl scenarios by running them against real APIs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import nullcontext
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from groundcontrol import config, pipeline
from groundcontrol.clients import get_fixtures_dir
from groundcontrol.clients.tavily import TavilyClient


def list_calls_for_dry_run(only: str | None = None) -> None:
    """List scenarios and calls that would be recorded in live mode."""
    scenarios_dir = get_fixtures_dir() / "scenarios"
    scenario_files = sorted(scenarios_dir.glob("*.json"))

    print("Dry run: Scenarios and API calls that would be recorded with LIVE=1:")
    for scen_file in scenario_files:
        try:
            data = json.loads(scen_file.read_text(encoding="utf-8"))
            sid = data.get("id", scen_file.stem)
            title = data.get("title", sid)
            applies = data.get("expected", {}).get("applies", False)
            amount = data.get("expected", {}).get("amount", 0)
        except Exception:
            sid = scen_file.stem
            title = sid
            applies = True
            amount = 0

        print(f"\nScenario: {sid} ({title})")
        print("  - [Nemotron] Chat completion: extract facts from input text")
        if applies:
            if only != "nemotron":
                if amount == 300:
                    print("  - [Tavily] Search: 'Regulation 261 2004 EUR 600 Article 7' on official domains")
                    print("  - [Tavily] Search: 'CJEU Sturgeon C-402/07 three hours or more' on curia/eur-lex")
                elif amount > 0:
                    print(f"  - [Tavily] Search: 'Regulation 261 2004 EUR {amount} Article 7' on official domains")

                print("  - [Tavily] Search: 'Regulation 261 2004 meals and refreshments Article 9' on official domains")
                if sid in ("cancel-short-notice", "delay-weather"):
                    print("  - [Tavily] Search: 'Regulation 261 2004 reimbursement Article 8' on official domains")

            print("  - [Nemotron] Chat completion: generate claim narrative statement")
        else:
            print("  (Flight outside EU261 scope: no verification or narrative calls)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record live fixtures for GroundControl")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List which scenarios and calls would be recorded without making API calls",
    )
    parser.add_argument("--only", choices=["nemotron"], help="Record only Nemotron; replay Tavily searches")
    args = parser.parse_args(argv)

    if args.dry_run:
        list_calls_for_dry_run(only=args.only)
        return 0

    if not config.is_live():
        print("Error: LIVE=1 environment variable is required to record fixtures.", file=sys.stderr)
        sys.exit(2)

    if not config.get_nebius_api_key():
        print("Error: NEBIUS_API_KEY environment variable is required to record fixtures.", file=sys.stderr)
        sys.exit(2)

    if args.only != "nemotron" and not config.get_tavily_api_key():
        print("Error: TAVILY_API_KEY environment variable is required to record fixtures.", file=sys.stderr)
        sys.exit(2)

    scenarios_dir = get_fixtures_dir() / "scenarios"
    scenario_files = sorted(scenarios_dir.glob("*.json"))
    if not scenario_files:
        print("Error: No scenarios found in fixtures/scenarios", file=sys.stderr)
        sys.exit(2)

    previous = os.environ.get("RECORD_FIXTURES")
    os.environ["RECORD_FIXTURES"] = "1"
    def replay_search(client, query, include_domains=None):
        return client._replay(client._build_payload(query, include_domains))

    search_context = (
        patch.object(TavilyClient, "search", replay_search)
        if args.only == "nemotron" else nullcontext()
    )
    try:
        with search_context:
            for scen_file in scenario_files:
                sid = scen_file.stem
                print(f"Recording scenario: {sid}...")
                pipeline.run_scenario(sid)
                print(f"Recorded scenario: {sid}")
    finally:
        # Recording must not outlive this call (in-process callers such as tests or the web app).
        if previous is None:
            os.environ.pop("RECORD_FIXTURES", None)
        else:
            os.environ["RECORD_FIXTURES"] = previous

    print("Fixture recording completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
