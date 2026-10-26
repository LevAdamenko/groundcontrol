"""Persistent access and cost controls; stores no judge code or model content."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import time

from groundcontrol.config import is_live, get_nebius_api_key, get_tavily_api_key

SESSION_SECONDS = 30 * 24 * 60 * 60


def available():
    return bool(is_live() and get_nebius_api_key() and get_tavily_api_key() and os.environ.get("JUDGE_CODE"))


@contextmanager
def database():
    directory = Path(os.environ.get("DATA_DIR", "./data"))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "live.sqlite3"
    # Create private before SQLite opens it, including when umask is permissive.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL)")
        connection.execute("CREATE TABLE IF NOT EXISTS failures (ip TEXT, at REAL)")
        connection.execute("CREATE TABLE IF NOT EXISTS runs (day TEXT PRIMARY KEY, count INTEGER)")
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def unlocked(token):
    if not available() or not token:
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    with database() as db:
        return db.execute("SELECT 1 FROM sessions WHERE token=? AND expires>?", (digest, time.time())).fetchone() is not None


def unlock(ip, valid):
    """Return (status, token); serialize attempts across concurrent requests."""
    now = time.time()
    with database() as db:
        db.execute("DELETE FROM failures WHERE at<=?", (now - 3600,))
        db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
        count = db.execute("SELECT COUNT(*) FROM failures WHERE ip=?", (ip,)).fetchone()[0]
        if count >= 10:
            return 429, None
        if not valid:
            db.execute("INSERT INTO failures VALUES (?, ?)", (ip, now))
            return 401, None
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?, ?)", (hashlib.sha256(token.encode()).hexdigest(), now + SESSION_SECONDS))
        return 200, token


def reserve_run():
    """Charge once before processing, including failed runs; never exceed the cap."""
    day = datetime.now(timezone.utc).date().isoformat()
    cap = max(0, int(os.environ.get("LIVE_DAILY_CAP", "300")))
    with database() as db:
        db.execute("INSERT OR IGNORE INTO runs VALUES (?, 0)", (day,))
        cursor = db.execute("UPDATE runs SET count=count+1 WHERE day=? AND count<?", (day, cap))
        return cursor.rowcount == 1
