"""Process state for the one open case: chat sessions, page sockets, and logging."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from meddataos.datactrl import tools
from meddataos.datactrl.case import Case


def log(who: str, message: str) -> None:
    """Print one log line, collapsed and cut so a long reply stays one line."""
    text = " ".join(message.split())

    if len(text) > 180:
        text = text[:177] + "..."

    print(f"{who:<6} {text}", flush=True)


def short_session(session_id: str) -> str:
    """The first characters of a session id, for log lines."""
    return session_id[:8] if session_id else "?"


@dataclass
class Session:
    """One conversation: its messages and whether a question is still being answered."""

    patient_id: str | None = None
    history: list[dict] = field(default_factory=list)
    processing: bool = False
    uploaded_file: str | None = None
    steps: list[dict] = field(default_factory=list)
    status: str = ""
    started: float | None = None

    def add(
        self,
        role: str,
        content: str,
        steps: list[dict] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Append one turn, stamped so the page can order it."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if steps:
            entry["steps"] = steps

        if duration_ms is not None:
            entry["duration_ms"] = duration_ms

        self.history.append(entry)

    def elapsed_ms(self) -> int | None:
        """Time since the open question was sent, measured on the server clock."""
        if self.started is None:
            return None

        return int((time.monotonic() - self.started) * 1000)


class Hub:
    """The page sockets for this process."""

    def __init__(self) -> None:
        """No pages are connected yet."""
        self.connections: set = set()

    def connect(self, websocket) -> None:
        """Remember one page socket."""
        self.connections.add(websocket)

    def disconnect(self, websocket) -> None:
        """Forget one page socket."""
        self.connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send one message to every open page."""
        if not self.connections:
            return

        await asyncio.gather(
            *[self._send(connection, message) for connection in list(self.connections)],
            return_exceptions=True,
        )

    async def assistant(
        self,
        session_id: str,
        message: str,
        steps: list[dict] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Push an agent reply to every open page."""
        message_out = {
            "type": "assistant",
            "session_id": session_id,
            "header": "System Response",
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "metadata": {},
        }

        if steps:
            message_out["steps"] = steps

        if duration_ms is not None:
            message_out["duration_ms"] = duration_ms

        await self.broadcast(message_out)

    async def step(self, session_id: str, step: dict, elapsed_ms: int | None) -> None:
        """Push one tool or consult step to every open page."""
        await self.broadcast({
            "type": "step",
            "session_id": session_id,
            "elapsed_ms": elapsed_ms,
            **step,
        })

    async def status(self, session_id: str, label: str, elapsed_ms: int | None) -> None:
        """Push what the open question is doing now, such as waiting on the model."""
        await self.broadcast({
            "type": "status",
            "session_id": session_id,
            "label": label,
            "elapsed_ms": elapsed_ms,
        })

    async def _send(self, connection, message: dict) -> None:
        try:
            await connection.send_json(message)
        except Exception:
            self.connections.discard(connection)


APP_ROOT = Path(__file__).resolve().parents[3]


class AppState:
    """The case, chat sessions, and sockets for this process."""

    def __init__(self) -> None:
        """Nothing is open until ``open`` is called."""
        self.root: Path | None = None
        self.report: dict | None = None
        self.profile: dict = {}
        self.sessions: dict[str, Session] = {}
        self.pins: dict[str, list] = {}
        self.reviews: dict[str, dict] = {}
        self.agent_url: str | None = None
        self.specialists: dict = {}
        self.consulted: dict[str, dict[str, dict]] = {}
        self.pending: set[str] = set()
        self.reads: dict[str, list[dict]] = {}
        self.calls: dict[str, dict[str, dict]] = {}
        self.cited: dict[str, dict[str, dict]] = {}
        self.runs: dict[str, dict] = {}
        self.datactrl_case: Case | None = None
        self.hub = Hub()

    def open(self, folder: str) -> Path:
        """Open ``folder`` with datactrl. One folder for the life of the process."""
        root = Path(folder).expanduser().resolve()

        if not root.is_dir():
            raise SystemExit(f"Not a folder: {root}")

        print(f"Opening {root}", flush=True)
        self.root = root
        self.report = tools.discover(str(root))
        self._load()
        return root

    def save(self) -> None:
        """Write chats, pins, and reviews for the open case to disk."""
        if self.root is None:
            return

        from meddataos.server import store

        store.save(self.root, self.sessions, self.pins, self.reviews)

    def _load(self) -> None:
        """Restore chats, pins, and reviews saved for this case."""
        from meddataos.server import store

        payload = store.load(self.root)
        self.sessions = store.sessions_from_store(payload["sessions"])
        self.pins = {
            key: list(value)
            for key, value in payload["pins"].items()
            if isinstance(key, str) and isinstance(value, list)
        }
        self.reviews = {
            key: dict(value)
            for key, value in payload["reviews"].items()
            if isinstance(key, str) and isinstance(value, dict)
        }

        if self.sessions or self.pins or self.reviews:
            print(
                f"Restored {len(self.sessions)} chat(s), "
                f"{sum(len(v) for v in self.pins.values())} pin(s), "
                f"{sum(len(v) for v in self.reviews.values())} review key(s)",
                flush=True,
            )

    def new_session(self, patient_id: str | None) -> str:
        """A new chat, optionally tied to one patient."""
        session_id = str(uuid4())
        self.sessions[session_id] = Session(patient_id=patient_id)
        self.save()
        return session_id

    def conversations(self, patient_id: str) -> list[dict]:
        """Chats for this patient, newest last, with a short preview of the question."""
        found = []

        for session_id, session in self.sessions.items():
            if session.patient_id != patient_id:
                continue

            preview = next(
                (
                    message["content"][:60]
                    for message in session.history
                    if message["role"] == "user"
                ),
                "",
            )
            found.append(
                {
                    "session_id": session_id,
                    "preview": preview or "New conversation",
                }
            )

        return found


state = AppState()
