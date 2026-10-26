"""Demo CLI runner for GroundControl."""
from __future__ import annotations

import argparse
import json
import os
import sys
from groundcontrol import pipeline
from groundcontrol.clients import get_fixtures_dir

SCENARIO_IDS = [
    "cancel-short-notice",
    "delay-3h40",
    "delay-weather",
    "longhaul-3h30",
    "outside-scope",
]


def check_recorded_fixtures() -> bool:
    """Check if existing fixtures were recorded live."""
    fixtures_dir = get_fixtures_dir()
    for subdir in ("nemotron", "tavily"):
        d = fixtures_dir / subdir
        if d.is_dir():
            for p in d.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("recorded") is True:
                        return True
                except Exception:
                    pass
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GroundControl EU261 offline demo")
    parser.add_argument("--offline", action="store_true", help="Force LIVE=0 offline replay mode")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario ID to inspect and print claim letter for")
    args = parser.parse_args(argv)

    if args.offline:
        os.environ["LIVE"] = "0"

    is_live = os.environ.get("LIVE", "0") == "1"
    is_recorded = check_recorded_fixtures()

    if is_live:
        print("mode: live API calls")
    elif is_recorded:
        print("mode: offline replay (recorded fixtures, recorded=true)")
    else:
        print("mode: offline replay (hand-written fixtures, recorded=false)")

    results: dict[str, pipeline.Result] = {}
    for sid in SCENARIO_IDS:
        res = pipeline.run_scenario(sid)
        results[sid] = res
        a = res.assessment
        applies = a.applies
        comp = a.compensation
        amount = comp.amount_eur if (applies and comp) else 0
        status = comp.status if (applies and comp) else "n/a"
        disputed = comp.disputed if (applies and comp) else False

        print(f"scenario: {sid:20s} | applies: {str(applies):5s} | amount: {amount:3d} EUR | status: {status:10s} | disputed: {str(disputed)}")

    target_scenario = args.scenario or ("delay-3h40" if "--scenario" in sys.argv else None)
    if target_scenario:
        if target_scenario not in results:
            print(f"\nScenario '{target_scenario}' not found. Available: {', '.join(SCENARIO_IDS)}", file=sys.stderr)
            return 1
        res = results[target_scenario]
        print(f"\n{'='*70}")
        print(f"CLAIM LETTER FOR SCENARIO: {target_scenario}")
        print(f"{'='*70}\n")
        print(res.claim)

    return 0


if __name__ == "__main__":
    sys.exit(main())
