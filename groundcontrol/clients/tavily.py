"""Tavily search client supporting live API calls and offline replay."""
from __future__ import annotations

import json
from pathlib import Path
from groundcontrol import clients, config
from groundcontrol.clients import FixtureMissing, MissingApiKey, post_json, stable_hash


class TavilyClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def _build_payload(self, query: str, include_domains: list[str] | tuple[str, ...] | None = None) -> dict:
        domains = sorted(list(include_domains)) if include_domains else []
        return {
            "include_domains": domains,
            "max_results": 5,
            "query": query,
        }

    def search(self, query: str, include_domains: list[str] | tuple[str, ...] | None = None) -> list[dict]:
        payload = self._build_payload(query, include_domains)
        req_hash = stable_hash(payload)

        if config.is_live():
            api_key = self._api_key or config.get_tavily_api_key()
            if not api_key:
                raise MissingApiKey("TAVILY_API_KEY environment variable is required when LIVE=1")

            post_body = {
                "api_key": api_key,
                "query": query,
                "include_domains": payload["include_domains"],
                "max_results": 5,
                # Free tier: basic depth costs 1 credit per search; never use "advanced".
                "search_depth": "basic",
            }
            data = post_json("Tavily", config.TAVILY_SEARCH_URL, json=post_body, timeout=60.0)
            if clients.is_recording():
                clients.record_fixture("tavily", req_hash, payload, data)
            return data.get("results", [])

        return self._replay(payload)

    def _replay(self, payload: dict) -> list[dict]:
        """Replay an existing search without contacting Tavily or recording."""
        req_hash = stable_hash(payload)
        fixture_path = clients.get_fixtures_dir() / "tavily" / f"{req_hash}.json"
        if not fixture_path.is_file():
            raise FixtureMissing(f"Tavily fixture missing for hash {req_hash} at {fixture_path}")

        try:
            fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise FixtureMissing(f"Error reading fixture {fixture_path}: {e}") from e

        resp_content = fixture_data.get("response")
        if isinstance(resp_content, dict) and "results" in resp_content:
            return resp_content["results"]
        if isinstance(resp_content, list):
            return resp_content
        return []
