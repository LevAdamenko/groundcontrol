"""Nemotron client supporting live Nebius Token Factory calls and offline replay."""
from __future__ import annotations

import json
from pathlib import Path
from groundcontrol import clients, config
from groundcontrol.clients import FixtureMissing, MissingApiKey, UpstreamError, post_json, stable_hash


class NemotronClient:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or config.get_nemotron_model()
        self.base_url = (base_url or config.get_nebius_base_url()).rstrip("/")

    def _build_payload(self, messages: list[dict], response_format: dict | None = None) -> dict:
        payload: dict = {
            "messages": messages,
            "model": self.model,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    def chat(self, messages: list[dict], response_format: dict | None = None) -> str:
        payload = self._build_payload(messages, response_format=response_format)
        req_hash = stable_hash(payload)

        if config.is_live():
            api_key = config.get_nebius_api_key()
            if not api_key:
                raise MissingApiKey("NEBIUS_API_KEY environment variable is required when LIVE=1")

            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = post_json("Nebius Token Factory", url, json=payload, headers=headers, timeout=60.0)
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                raise UpstreamError("Nebius Token Factory returned no completion") from e
            if clients.is_recording():
                clients.record_fixture("nemotron", req_hash, payload, data)
            return content

        fixture_path = clients.get_fixtures_dir() / "nemotron" / f"{req_hash}.json"
        if not fixture_path.is_file():
            raise FixtureMissing(f"Nemotron fixture missing for hash {req_hash} at {fixture_path}")

        try:
            fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise FixtureMissing(f"Error reading fixture {fixture_path}: {e}") from e

        resp_content = fixture_data.get("response")
        if isinstance(resp_content, dict) and "choices" in resp_content:
            return resp_content["choices"][0]["message"]["content"]
        if isinstance(resp_content, str):
            return resp_content
        return str(resp_content or "")
