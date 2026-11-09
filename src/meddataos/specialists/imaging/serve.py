"""Serve the imaging agent at POST /v1/chat/completions.

The new MedDataOS server registers this process as the imaging specialist.
It does what the old page did: pick one DICOM series, render one slice, and
describe that slice. The reply is citation JSON for that series file.

    python -m meddataos.specialists.imaging.serve --case /path/to/TCGA-DD-A4NF

The vision read uses the Azure OpenAI deployment when AZURE_OPENAI_API_KEY,
AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_DEPLOYMENT are set (it must accept images),
otherwise Gemini (GEMINI_API_KEY, GEMINI_MODEL).
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import meddataos.specialists.common  # noqa: F401  (loads .env)
from meddataos.datactrl import Case

from meddataos.specialists.imaging.read import read_slice


def web_path(relative: str) -> str:
    parts = [quote(part) for part in Path(relative).parts if part not in ("", ".")]
    return "/case/" + "/".join(parts)


def _mark(summary: str, cite_id: str = "1") -> str:
    """Put the marker after the first sentence, not on its own.

    A sentence ends at ., ! or ? followed by a space or the end, so a dot inside
    "2.0" or a series UID is not a boundary.
    """
    text = " ".join(summary.split())
    match = re.search(r"[.!?](?=\s|$)", text)
    if not match:
        return f"{text} [cite:{cite_id}]."
    return text[: match.start()].rstrip() + f" [cite:{cite_id}]" + text[match.start() :]


def cited_reply(read) -> str:
    """Citation JSON when a series was chosen, otherwise plain text."""
    if not read.series_path:
        return read.summary

    citation = {
        "id": "1",
        "agent": "imaging",
        "file": Path(read.series_path).name or read.file,
        "web_path": web_path(read.series_path),
        "summary": read.summary,
    }
    if read.preview:
        citation["preview"] = read.preview
    return json.dumps(
        {"response": _mark(read.summary), "citations": [citation]},
        ensure_ascii=False,
    )


def question_from(messages: list) -> str:
    """The latest user question, skipping a citation-correction turn."""
    users = [
        message.get("content")
        for message in messages
        if isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(message.get("content"), str)
    ]
    for text in reversed(users):
        if not text.startswith("The server refused"):
            return text.strip()
    return (users[-1] if users else "").strip()


class Handler(BaseHTTPRequestHandler):
    case: Case
    patient_id: str

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        question = question_from(body.get("messages") or [])
        print(f"imaging  question: {question}", flush=True)

        if question == "Fill in the patient card.":
            self._send({"choices": [{"message": {
                "role": "assistant",
                "content": json.dumps({
                    "name": self.patient_id,
                    "age": "",
                    "sex": "",
                    "blood_type": None,
                    "allergies": [],
                    "conditions": [],
                    "data_dates": {},
                }),
            }}]})
            return

        try:
            read = read_slice(self.case, question)
            content = cited_reply(read)
            print(f"imaging  series={read.series_id or '-'} chars={len(content)}", flush=True)
        except Exception as exc:
            content = f"The imaging agent failed: {exc}"
            print(f"imaging  failed: {exc}", flush=True)

        self._send({"choices": [{"message": {"role": "assistant", "content": content}}]})

    def _send(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        print(f"imaging  {args[0]}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Imaging specialist")
    parser.add_argument("--case", required=True, help="Case folder to open")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()

    root = Path(args.case).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a folder: {root}")

    Handler.case = Case.open(root)
    Handler.patient_id = root.name
    series = Handler.case.report.dicom
    print(f"Imaging agent: {len(series)} series in {root}", flush=True)
    print(f"Patient: {Handler.patient_id}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    host, port = server.server_address
    print(f"Agent: http://{host}:{port}/v1", flush=True)
    print(
        "Imaging only: pass that URL as --agent-url when you start the page.",
        flush=True,
    )
    print(
        "With the notes agent, keep a router as --agent-url and add "
        f"--specialist imaging=http://{host}:{port}/v1",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
