"""
SQLite is a database that's just a single file on disk (no separate server process to run, unlike Postgres/MySQL). 
It's built into Python already — no extra service to install or manage.
SQLite is a lightweight, serverless relational database engine, and the reason you don't need to install it is because Python
comes with SQLite built directly into its core standard library.
"""
#Python's built-in library for talking to SQLite databases. No install needed, unlike psycopg2 for Postgres.
import sqlite3
import json
from datetime import datetime, timezone

from trip_slots import TripSlots

DB_FILE = "sessions.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    # check_same_thread=False lets FastAPI (which may handle requests on
    # different threads) safely reuse this connection function
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db():
    """Create every table the app needs, if it doesn't already exist."""
    conn = get_connection()

    # chat conversation state
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id    TEXT PRIMARY KEY,
            slots_json    TEXT NOT NULL,
            last_question TEXT,
            messages_json TEXT,              -- full [{role, text}] transcript
            updated_at    TEXT
        )
    """)
    # migrate older DBs that predate the transcript columns
    _existing = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
    if "messages_json" not in _existing:
        conn.execute("ALTER TABLE sessions ADD COLUMN messages_json TEXT")
    if "updated_at" not in _existing:
        conn.execute("ALTER TABLE sessions ADD COLUMN updated_at TEXT")

    # user accounts — one row per person who signs up
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            name          TEXT NOT NULL,
            password_hash TEXT NOT NULL,      -- bcrypt hash, never the password
            created_at    TEXT NOT NULL
        )
    """)

    # saved trip plans — this is the "History" the UI shows
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            title        TEXT,
            source       TEXT, destination TEXT, travel_date TEXT,
            source_lat   REAL, source_lon  REAL,
            dest_lat     REAL, dest_lon    REAL,
            result_json  TEXT NOT NULL,      -- the full check_all_modes() output
            created_at   TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id)")

    conn.commit()
    conn.close()


def load_session(session_id: str) -> dict | None:
    """{"slots": TripSlots, "last_question": str|None, "messages": list} or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT slots_json, last_question, messages_json FROM sessions WHERE session_id = ?",
        (session_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    slots_json, last_question, messages_json = row
    return {
        "slots": TripSlots(**json.loads(slots_json)),
        "last_question": last_question,
        "messages": json.loads(messages_json) if messages_json else [],
    }


def save_session(session_id: str, slots: TripSlots, last_question: str | None,
                 messages: list | None = None):
    """Upsert the session: slots + last question + full chat transcript."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO sessions (session_id, slots_json, last_question, messages_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            slots_json    = excluded.slots_json,
            last_question = excluded.last_question,
            messages_json = excluded.messages_json,
            updated_at    = excluded.updated_at
    """, (
        session_id, slots.model_dump_json(), last_question,
        json.dumps(messages or []), _now_iso(),
    ))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
def _row_to_user(row) -> dict:
    return {"id": row[0], "email": row[1], "name": row[2],
            "password_hash": row[3], "created_at": row[4]}


def create_user(email: str, name: str, password_hash: str) -> dict:
    """Insert a new user. Raises sqlite3.IntegrityError if the email is taken."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (email.lower().strip(), name.strip(), password_hash, _now_iso()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "email": email.lower().strip(), "name": name.strip()}


def get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, name, password_hash, created_at FROM users WHERE email = ?",
        (email.lower().strip(),),
    ).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, email, name, password_hash, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return _row_to_user(row) if row else None


# --------------------------------------------------------------------------
# Trips (saved plans = the History feature)
# --------------------------------------------------------------------------
def save_trip(user_id: int, meta: dict, result: dict) -> dict:
    """
    meta  = {title, source, destination, travel_date,
             source_lat, source_lon, dest_lat, dest_lon}
    result = the dict returned by connectivity.check_all_modes()
    """
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO trips (user_id, title, source, destination, travel_date,
                           source_lat, source_lon, dest_lat, dest_lon,
                           result_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, meta.get("title"), meta.get("source"), meta.get("destination"),
        meta.get("travel_date"),
        meta.get("source_lat"), meta.get("source_lon"),
        meta.get("dest_lat"), meta.get("dest_lon"),
        json.dumps(result), _now_iso(),
    ))
    conn.commit()
    trip_id = cur.lastrowid
    conn.close()
    return get_trip(user_id, trip_id)


def list_trips(user_id: int) -> list[dict]:
    """Newest first. Summary only (no heavy result_json) for the history list."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, title, source, destination, travel_date, created_at
        FROM trips WHERE user_id = ? ORDER BY id DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "source": r[2], "destination": r[3],
         "travel_date": r[4], "created_at": r[5]}
        for r in rows
    ]


def get_trip(user_id: int, trip_id: int) -> dict | None:
    """Full trip including the parsed result JSON. Scoped to the owner."""
    conn = get_connection()
    row = conn.execute("""
        SELECT id, title, source, destination, travel_date,
               source_lat, source_lon, dest_lat, dest_lon, result_json, created_at
        FROM trips WHERE id = ? AND user_id = ?
    """, (trip_id, user_id)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0], "title": row[1], "source": row[2], "destination": row[3],
        "travel_date": row[4],
        "source_lat": row[5], "source_lon": row[6],
        "dest_lat": row[7], "dest_lon": row[8],
        "result": json.loads(row[9]),
        "created_at": row[10],
    }


def delete_trip(user_id: int, trip_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted