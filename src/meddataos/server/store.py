"""SQLite persistence and audit runs for the open case under data/cases/."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from meddataos.server.state import APP_ROOT, Session, log

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    patient_id TEXT,
    history TEXT NOT NULL,
    uploaded_file TEXT
);

CREATE TABLE IF NOT EXISTS pins (
    patient_id TEXT NOT NULL,
    pin_id TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (patient_id, pin_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    patient_id TEXT NOT NULL,
    review_key TEXT NOT NULL,
    checklist_state TEXT NOT NULL,
    PRIMARY KEY (patient_id, review_key)
);

CREATE TABLE IF NOT EXISTS audit_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    patient_id TEXT,
    question TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    duration_ms INTEGER,
    outcome TEXT NOT NULL,
    steps TEXT NOT NULL,
    calls TEXT NOT NULL,
    refusals TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_runs(session_id, started_at);
CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_runs(patient_id, started_at);
"""


def case_dir(root: Path) -> Path:
    """Folder under data/cases for this case path."""
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return APP_ROOT / "data" / "cases" / digest


def db_path(root: Path) -> Path:
    """SQLite file for ``root``."""
    return case_dir(root) / "store.db"


def _connect(root: Path) -> sqlite3.Connection:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(_SCHEMA)
    connection.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('case', ?)",
        (str(root.resolve()),),
    )
    connection.commit()
    return connection


def _migrate_json(root: Path) -> None:
    """Import a legacy store.json into SQLite once."""
    legacy = case_dir(root) / "store.json"
    database = db_path(root)

    if not legacy.is_file() or database.is_file():
        return

    try:
        payload = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log("server", f"could not migrate legacy store {legacy}: {exc}")
        return

    if not isinstance(payload, dict):
        return

    sessions = payload.get("sessions") if isinstance(payload.get("sessions"), dict) else {}
    pins = payload.get("pins") if isinstance(payload.get("pins"), dict) else {}
    reviews = payload.get("reviews") if isinstance(payload.get("reviews"), dict) else {}
    found = sessions_from_store(sessions)

    save(root, found, pins, reviews)
    backup = legacy.with_suffix(".json.bak")

    try:
        legacy.replace(backup)
        log("server", f"migrated legacy store to {database}")
    except OSError as exc:
        log("server", f"could not rename legacy store {legacy}: {exc}")


def load(root: Path) -> dict:
    """Read sessions, pins, and reviews for ``root``."""
    _migrate_json(root)

    if not db_path(root).is_file():
        return {"sessions": {}, "pins": {}, "reviews": {}}

    try:
        with _connect(root) as connection:
            sessions = {
                row["session_id"]: {
                    "patient_id": row["patient_id"],
                    "history": json.loads(row["history"]),
                    "uploaded_file": row["uploaded_file"],
                }
                for row in connection.execute(
                    "SELECT session_id, patient_id, history, uploaded_file FROM sessions"
                )
            }
            pins: dict[str, list] = {}

            for row in connection.execute("SELECT patient_id, pin_id, data FROM pins"):
                entry = json.loads(row["data"])
                pins.setdefault(row["patient_id"], []).append(entry)

            reviews: dict[str, dict] = {}

            for row in connection.execute(
                "SELECT patient_id, review_key, checklist_state FROM reviews"
            ):
                reviews.setdefault(row["patient_id"], {})[row["review_key"]] = json.loads(
                    row["checklist_state"]
                )
    except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        log("server", f"could not read case store {db_path(root)}: {exc}")
        return {"sessions": {}, "pins": {}, "reviews": {}}

    return {"sessions": sessions, "pins": pins, "reviews": reviews}


def save(root: Path, sessions: dict[str, Session], pins: dict, reviews: dict) -> None:
    """Write sessions, pins, and reviews for ``root``. Audit runs are append-only."""
    try:
        with _connect(root) as connection:
            connection.execute("DELETE FROM sessions")
            connection.execute("DELETE FROM pins")
            connection.execute("DELETE FROM reviews")

            for session_id, session in sessions.items():
                connection.execute(
                    """
                    INSERT INTO sessions(session_id, patient_id, history, uploaded_file)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        session.patient_id,
                        json.dumps(session.history, ensure_ascii=False),
                        session.uploaded_file,
                    ),
                )

            for patient_id, patient_pins in pins.items():
                if not isinstance(patient_pins, list):
                    continue

                for pin in patient_pins:
                    if not isinstance(pin, dict) or not pin.get("pin_id"):
                        continue

                    connection.execute(
                        """
                        INSERT INTO pins(patient_id, pin_id, data)
                        VALUES (?, ?, ?)
                        """,
                        (
                            patient_id,
                            pin["pin_id"],
                            json.dumps(pin, ensure_ascii=False),
                        ),
                    )

            for patient_id, patient_reviews in reviews.items():
                if not isinstance(patient_reviews, dict):
                    continue

                for key, checklist in patient_reviews.items():
                    connection.execute(
                        """
                        INSERT INTO reviews(patient_id, review_key, checklist_state)
                        VALUES (?, ?, ?)
                        """,
                        (
                            patient_id,
                            key,
                            json.dumps(checklist, ensure_ascii=False),
                        ),
                    )

            connection.commit()
    except (OSError, sqlite3.Error) as exc:
        log("server", f"could not write case store {db_path(root)}: {exc}")


def sessions_from_store(raw: dict) -> dict[str, Session]:
    """Build Session objects from stored data. In-flight flags stay clear."""
    found: dict[str, Session] = {}

    for session_id, entry in raw.items():
        if not isinstance(session_id, str) or not isinstance(entry, dict):
            continue

        history = entry.get("history")
        uploaded = entry.get("uploaded_file")
        found[session_id] = Session(
            patient_id=entry.get("patient_id"),
            history=list(history) if isinstance(history, list) else [],
            processing=False,
            uploaded_file=uploaded if isinstance(uploaded, str) else None,
        )

    return found


def append_audit_run(root: Path, record: dict) -> str:
    """Append one answered question audit record. Returns ``run_id``."""
    run_id = record.get("run_id") or uuid4().hex

    try:
        with _connect(root) as connection:
            connection.execute(
                """
                INSERT INTO audit_runs(
                    run_id, session_id, patient_id, question, started_at, finished_at,
                    duration_ms, outcome, steps, calls, refusals, answer, citations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record["session_id"],
                    record.get("patient_id"),
                    record["question"],
                    record["started_at"],
                    record.get("finished_at") or datetime.now(UTC).isoformat(),
                    record.get("duration_ms"),
                    record.get("outcome", "success"),
                    json.dumps(record.get("steps") or [], ensure_ascii=False),
                    json.dumps(record.get("calls") or [], ensure_ascii=False),
                    json.dumps(record.get("refusals") or [], ensure_ascii=False),
                    record.get("answer") or "",
                    json.dumps(record.get("citations") or [], ensure_ascii=False),
                ),
            )
            connection.commit()
    except (OSError, sqlite3.Error) as exc:
        log("server", f"could not write audit run to {db_path(root)}: {exc}")

    return run_id


def list_audit_runs(
    root: Path,
    *,
    session_id: str | None = None,
    patient_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return audit runs newest first, optionally scoped to one session or patient."""
    if not db_path(root).is_file():
        return []

    limit = max(1, min(int(limit), 500))
    query = (
        "SELECT run_id, session_id, patient_id, question, started_at, finished_at, "
        "duration_ms, outcome, steps, calls, refusals, answer, citations "
        "FROM audit_runs"
    )
    params: list = []
    clauses: list[str] = []

    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)

    if patient_id:
        clauses.append("patient_id = ?")
        params.append(patient_id)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    try:
        with _connect(root) as connection:
            rows = connection.execute(query, params).fetchall()
    except (OSError, sqlite3.Error) as exc:
        log("server", f"could not read audit runs from {db_path(root)}: {exc}")
        return []

    runs = []

    for row in rows:
        runs.append({
            "run_id": row["run_id"],
            "session_id": row["session_id"],
            "patient_id": row["patient_id"],
            "question": row["question"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "duration_ms": row["duration_ms"],
            "outcome": row["outcome"],
            "steps": json.loads(row["steps"]),
            "calls": json.loads(row["calls"]),
            "refusals": json.loads(row["refusals"]),
            "answer": row["answer"],
            "citations": json.loads(row["citations"]),
        })

    return runs


def calls_for_audit(calls: dict[str, dict]) -> list[dict]:
    """Tool-call metadata for export, without file bodies or spans."""
    found = []

    for token, record in calls.items():
        if not isinstance(record, dict):
            continue

        found.append({
            "cite": token,
            "tool": record.get("tool"),
            "web_path": record.get("web_path"),
            "modality": record.get("modality"),
            "file": record.get("file"),
        })

    return found


def citations_for_audit(message: str) -> list[dict]:
    """Citation summaries from a delivered answer, without evidence quotes."""
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return []

    citations = parsed.get("citations") if isinstance(parsed, dict) else None

    if not isinstance(citations, list):
        return []

    kept = []

    for item in citations:
        if not isinstance(item, dict):
            continue

        kept.append({
            key: item[key]
            for key in ("cite", "id", "kind", "web_path", "summary", "agent", "inputs")
            if key in item
        })

    return kept

