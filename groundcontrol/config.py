"""Configuration and environment management for GroundControl."""
from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path


def _load_secrets_env() -> None:
    """Load ~/.config/hackathon/secrets.env if it exists without overwriting set env vars."""
    secrets_path = Path.home() / ".config" / "hackathon" / "secrets.env"
    try:
        if secrets_path.is_file():
            content = secrets_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except (OSError, PermissionError):
        # Gracefully handle sandbox restriction or missing file
        pass


_load_secrets_env()


WEB_MODE: ContextVar[bool | None] = ContextVar("web_mode", default=None)


def is_live() -> bool:
    """Use the request-local web mode, otherwise the CLI LIVE environment flag."""
    override = WEB_MODE.get()
    return override if override is not None else os.environ.get("LIVE", "0") == "1"


def get_nebius_api_key() -> str | None:
    return os.environ.get("NEBIUS_API_KEY")


def get_tavily_api_key() -> str | None:
    return os.environ.get("TAVILY_API_KEY")


def get_nemotron_model() -> str:
    return os.environ.get("NEMOTRON_MODEL", "nvidia/nemotron-3-super-120b-a12b")


def get_nebius_base_url() -> str:
    return os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
