"""Vercel entrypoint (zero-config FastAPI preset): the replay-only public demo.

LIVE is forced off before the app is imported, so the hosted demo never calls
Token Factory or Tavily and needs no keys — it answers from recorded fixtures.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["LIVE"] = "0"
os.environ["GROUNDCONTROL_FIXTURES_DIR"] = str(ROOT / "fixtures")

from groundcontrol.web import app  # noqa: E402

__all__ = ["app"]
