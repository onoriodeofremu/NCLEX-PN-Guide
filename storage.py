"""Storage backend for accounts and progress.

Uses a free hosted Postgres database (e.g. Supabase's free tier) when one is
configured via st.secrets["database"]["url"], and automatically falls back to
local JSON files next to the app when it isn't. This means:

- Zero setup still works — nothing breaks if no database is configured.
- The moment a database URL is added (see README.md), storage becomes
  permanent and independent of whichever host runs the app — no code
  changes needed either way, and nothing else in the app needs to know
  which mode it's in.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

DATA_DIR = Path(__file__).parent
USERS_FILE = DATA_DIR / "users.json"
PROGRESS_DIR = DATA_DIR / "progress"
PROGRESS_DIR.mkdir(exist_ok=True)


def _db_url() -> str | None:
    try:
        return st.secrets["database"]["url"]
    except Exception:
        return None


@st.cache_resource
def _get_conn():
    """Returns a live Postgres connection if a database is configured and
    reachable, else None (in which case every function below transparently
    uses local files instead)."""
    url = _db_url()
    if not url:
        import sys
        print("[storage] No [database] url found in st.secrets - using local files. "
              "If you expected a database, check Settings -> Secrets on Streamlit Cloud.",
              file=sys.stderr, flush=True)
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    salt TEXT NOT NULL,
                    hash TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS progress (
                    uid_hash TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                );
            """)
        return conn
    except Exception as e:
        # Printed (not raised) so the app keeps working on local files even
        # when the database can't connect. On Streamlit Community Cloud,
        # this line shows up in "Manage app" -> the logs panel, which is
        # the fastest way to see the *real* reason a connection failed
        # (bad password, wrong host, SSL required, etc.) instead of guessing.
        # flush=True + stderr: stdout is block-buffered (not line-buffered)
        # inside Streamlit Cloud's container, so a plain print() can sit in
        # a buffer and never reach the visible log stream until the process
        # exits. Writing to stderr and forcing a flush makes sure this
        # actually shows up right away.
        import sys
        print(f"[storage] Database connection failed, falling back to local files: {e!r}", file=sys.stderr, flush=True)
        return None


def using_database() -> bool:
    """True once a database is connected — lets the UI say so."""
    return _get_conn() is not None


# ---------------------------------------------------------------------------
# Accounts (username/password)
# ---------------------------------------------------------------------------
def _load_users_file() -> dict:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_users_file(users: dict) -> None:
    try:
        USERS_FILE.write_text(json.dumps(users))
    except Exception:
        pass  # read-only filesystem on some hosts; account won't persist there


def get_user(username: str) -> dict | None:
    conn = _get_conn()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT salt, hash FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                return {"salt": row[0], "hash": row[1]} if row else None
        except Exception:
            return None
    return _load_users_file().get(username)


def username_exists(username: str) -> bool:
    return get_user(username) is not None


def create_user(username: str, salt_hex: str, hash_hex: str) -> None:
    conn = _get_conn()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, salt, hash) VALUES (%s, %s, %s)",
                    (username, salt_hex, hash_hex),
                )
            return
        except Exception:
            pass  # fall through to the file backend if the write failed
    users = _load_users_file()
    users[username] = {"salt": salt_hex, "hash": hash_hex}
    _save_users_file(users)


# ---------------------------------------------------------------------------
# Per-account progress (keyed by a hash of the account id — never the raw
# email/username; see app.py's load_progress/save_progress)
# ---------------------------------------------------------------------------
def get_progress(uid_hash: str) -> dict | None:
    conn = _get_conn()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM progress WHERE uid_hash = %s", (uid_hash,))
                row = cur.fetchone()
                return row[0] if row else None  # psycopg2 parses jsonb -> dict automatically
        except Exception:
            return None
    path = PROGRESS_DIR / f"{uid_hash}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def save_progress(uid_hash: str, data: dict) -> None:
    conn = _get_conn()
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO progress (uid_hash, data) VALUES (%s, %s)
                    ON CONFLICT (uid_hash) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (uid_hash, json.dumps(data)),
                )
            return
        except Exception:
            pass  # fall through to the file backend if the write failed
    path = PROGRESS_DIR / f"{uid_hash}.json"
    try:
        path.write_text(json.dumps(data))
    except Exception:
        pass