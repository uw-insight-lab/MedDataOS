"""Start the whole stack for one case: router, specialists, and web server.

    pixi run stack data/TCGA-DD-A4NF
    pixi run stack data/RADCURE-0006 --only notes

The router is examples/agent.py. The specialists come from configs/agents.toml, and
their ports are read from the url in that file. Output from each process is
prefixed with its name. Ctrl-C stops everything.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
AGENTS_FILE = ROOT / "configs" / "agents.toml"
ROUTER_PORT = 8001
SPECIALIST_MODULES = {
    "notes": "meddataos.specialists.notes.serve",
    "imaging": "meddataos.specialists.imaging.serve",
}


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def _wait_for_port(host: str, port: int, proc: subprocess.Popen, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        if not _port_is_free(host, port):
            return True
        time.sleep(0.25)
    return False


def _pump(name: str, proc: subprocess.Popen) -> None:
    for line in proc.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def _spawn(name: str, argv: list[str], env: dict[str, str]) -> subprocess.Popen:
    proc = subprocess.Popen(
        argv,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=_pump, args=(name, proc), daemon=True).start()
    return proc


def _stop(procs: dict[str, subprocess.Popen]) -> None:
    for proc in procs.values():
        if proc.poll() is None:
            proc.terminate()
    deadline = time.time() + 10
    for proc in procs.values():
        try:
            proc.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            proc.kill()


def _model_warning(env: dict[str, str]) -> str | None:
    azure = all(env.get(k) for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"))
    if azure or env.get("GEMINI_API_KEY"):
        return None
    return "Neither GEMINI_API_KEY nor the AZURE_OPENAI_* settings are set, so the specialists cannot call a model."


def main() -> int:
    parser = argparse.ArgumentParser(description="Start MedDataOS with its router and specialists")
    parser.add_argument("case", help="Case folder to open, such as data/TCGA-DD-A4NF")
    parser.add_argument(
        "--only",
        help="Comma-separated specialists to start. Default is every one in configs/agents.toml.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("PYTHONSAFEPATH", None)

    case = Path(args.case).expanduser().resolve()
    if not case.is_dir():
        print(f"Case folder not found: {case}", file=sys.stderr)
        return 2

    with AGENTS_FILE.open("rb") as handle:
        registry = tomllib.load(handle)
    wanted = [n.strip() for n in args.only.split(",")] if args.only else list(registry)
    unknown = [n for n in wanted if n not in registry or n not in SPECIALIST_MODULES]
    if unknown:
        print(f"Unknown specialist: {', '.join(unknown)}. Available: {', '.join(registry)}", file=sys.stderr)
        return 2

    web_port = int(env.get("PORT", "8080"))
    ports = {"router": ROUTER_PORT, "server": web_port}
    for name in wanted:
        ports[name] = urlparse(registry[name]["url"]).port
    busy = [f"{name} (port {port})" for name, port in ports.items() if not _port_is_free("127.0.0.1", port)]
    if busy:
        print(f"Already in use: {', '.join(busy)}. Stop what is using them or change PORT in .env.", file=sys.stderr)
        return 2

    warning = _model_warning(env)
    if warning:
        print(f"Warning: {warning}", file=sys.stderr)

    # The server only sees the specialists that are actually running.
    chosen = Path(tempfile.mkdtemp()) / "agents.toml"
    chosen.write_text(
        "".join(
            f"[{n}]\nurl = {json.dumps(registry[n]['url'])}\n"
            f"description = {json.dumps(registry[n]['description'])}\n\n"
            for n in wanted
        )
    )

    procs: dict[str, subprocess.Popen] = {}
    stopping = threading.Event()

    def shutdown(*_: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        procs["router"] = _spawn(
            "router", [sys.executable, "examples/agent.py", "--port", str(ROUTER_PORT)], env
        )
        for name in wanted:
            procs[name] = _spawn(
                name,
                [sys.executable, "-m", SPECIALIST_MODULES[name], "--case", str(case), "--port", str(ports[name])],
                env,
            )
        for name, proc in list(procs.items()):
            if not _wait_for_port("127.0.0.1", ports[name], proc, 60):
                print(f"{name} did not start. See its output above.", file=sys.stderr)
                return 1

        procs["server"] = _spawn(
            "server",
            [
                sys.executable,
                "-m",
                "meddataos.server",
                str(case),
                "--agent-url",
                f"http://127.0.0.1:{ROUTER_PORT}/v1",
                "--agents",
                str(chosen),
            ],
            env,
        )

        while not stopping.is_set():
            for name, proc in procs.items():
                if proc.poll() is not None:
                    print(f"{name} exited with code {proc.returncode}. Stopping the stack.", file=sys.stderr)
                    return 1
            time.sleep(0.5)
        return 0
    finally:
        _stop(procs)


if __name__ == "__main__":
    raise SystemExit(main())
