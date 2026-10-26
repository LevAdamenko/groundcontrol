"""Small HTTP adapter for the GroundControl pipeline."""
from dataclasses import asdict
import json
import hmac
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundcontrol import pipeline
from groundcontrol.clients import FixtureMissing, UpstreamError, get_fixtures_dir
from groundcontrol.config import WEB_MODE, is_live
from groundcontrol import live_access
from groundcontrol.demo import SCENARIO_IDS
from groundcontrol.models import Entitlement

app = FastAPI(title="GroundControl")
OFFLINE_DETAIL = "offline mode: no recorded fixture for this text; pick a scenario or run with LIVE=1"
# Caps what one request can send to Nemotron in live mode; recorded scenarios are under 600 chars.
MAX_TEXT_CHARS = 4000
UPSTREAM_DETAIL = "Live service unavailable. Try again or pick a recorded flight."


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # FastAPI's default errors echo submitted inputs (including possible secrets).
    return JSONResponse({"detail": "Invalid request body"}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    # Return no exception details to the client.
    return JSONResponse({"error": "request_failed"}, status_code=500)


@app.get("/api/config")
def config(request: Request):
    return {"live_available": live_access.available(), "live_unlocked": live_access.unlocked(request.cookies.get("live_session"))}


@app.post("/api/unlock")
async def unlock(request: Request):
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        body = None
    code = body.get("code") if isinstance(body, dict) else None
    expected = os.environ.get("JUDGE_CODE", "")
    valid = isinstance(code, str) and hmac.compare_digest(code.encode(), expected.encode()) and live_access.available()
    # Last hop is the one our reverse proxy appended; earlier hops are client-controlled.
    ip = request.headers.get("x-forwarded-for", "").split(",")[-1].strip() or (request.client.host if request.client else "unknown")
    status, token = live_access.unlock(ip, valid)
    if status != 200:
        return JSONResponse({"error": "live_locked"}, status_code=status)
    response = JSONResponse({"live_unlocked": True})
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip().lower()
    response.set_cookie("live_session", token, max_age=live_access.SESSION_SECONDS, httponly=True, samesite="lax", secure=scheme == "https")
    return response


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str | None = None
    text: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)

    @model_validator(mode="after")
    def exactly_one(self):
        if len(self.model_fields_set) != 1 or (self.scenario_id is None and self.text is None):
            raise ValueError("Provide exactly one of scenario_id or text")
        return self


def serialize_entitlement(entitlement: Entitlement) -> dict:
    return {**asdict(entitlement), "status": entitlement.status}


def serialize_result(result: pipeline.Result) -> dict:
    data = asdict(result)
    assessment = data["assessment"]
    original = result.assessment
    assessment["compensation"] = serialize_entitlement(original.compensation) if original.compensation else None
    assessment["care"] = [serialize_entitlement(item) for item in original.care]
    assessment["refund_or_rerouting"] = serialize_entitlement(original.refund_or_rerouting) if original.refund_or_rerouting else None
    return {"mode": "live" if is_live() else "offline", **data}


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/info")
def info():
    return {"mode": "live" if live_access.available() else "offline"}


@app.get("/api/scenarios")
def scenarios():
    items = []
    for scenario_id in SCENARIO_IDS:
        data = json.loads((get_fixtures_dir() / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8"))
        items.append({key: data[key] for key in ("id", "title", "input_text")})
    return items


def process(body: RunRequest, request: Request, force_live=False):
    if body.scenario_id is not None and body.scenario_id not in SCENARIO_IDS:
        raise HTTPException(404, "Unknown scenario")
    live = force_live or (body.text is not None and is_live())
    if live:
        if not live_access.unlocked(request.cookies.get("live_session")):
            return JSONResponse({"error": "live_locked"}, status_code=401)
        if not live_access.reserve_run():
            return JSONResponse({"error": "live_daily_cap"}, status_code=429)
    mode = WEB_MODE.set(live)
    try:
        result = pipeline.run_scenario(body.scenario_id) if body.scenario_id is not None else pipeline.run(body.text)
        data = serialize_result(result)
        if live and result.assessment.verification_error:
            data["assessment"]["verification_error"] = "Official-source check unavailable"
        return redact(data)
    except FixtureMissing:
        raise HTTPException(409, OFFLINE_DETAIL) from None
    except UpstreamError:
        raise HTTPException(502, UPSTREAM_DETAIL) from None
    except Exception:
        return JSONResponse({"error": "request_failed"}, status_code=500)
    finally:
        WEB_MODE.reset(mode)


def redact(value):
    """Keep configured credentials out of responses even if echoed by an upstream."""
    if isinstance(value, str):
        for name in ("JUDGE_CODE", "NEBIUS_API_KEY", "TAVILY_API_KEY"):
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret, "[redacted]")
    elif isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    elif isinstance(value, list):
        return [redact(item) for item in value]
    return value


@app.post("/api/run")
def run(body: RunRequest, request: Request):
    return process(body, request)


@app.post("/api/live/run")
def live_run(body: RunRequest, request: Request):
    return process(body, request, force_live=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
