"""Azure OpenAI chat completions, shared by the specialists.

Used instead of Gemini when AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and
AZURE_OPENAI_DEPLOYMENT are all set. AZURE_OPENAI_API_VERSION is the date in
the query string (default 2024-10-21).
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

import meddataos.specialists.common  # noqa: F401  (loads .env)

# Tries for a name lookup that fails before Azure is reached.
DNS_ATTEMPTS = 4


def azure_configured() -> bool:
    """True when the three required Azure OpenAI settings are present."""
    return bool(
        os.getenv("AZURE_OPENAI_API_KEY")
        and os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_DEPLOYMENT")
    )


def azure_chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    json_mode: bool = False,
) -> dict:
    """One Azure chat completion. Returns the assistant message."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    deployment = quote(os.environ["AZURE_OPENAI_DEPLOYMENT"], safe="")
    version = quote(os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"), safe="")
    url = (
        f"{endpoint}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={version}"
    )
    body: dict[str, Any] = {"messages": messages, "temperature": 0}
    if tools:
        body["tools"] = tools
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    # Some reasoning models refuse function tools unless this is "none".
    if os.getenv("AZURE_OPENAI_REASONING_EFFORT"):
        body["reasoning_effort"] = os.environ["AZURE_OPENAI_REASONING_EFFORT"]

    message = _post_azure(url, body)
    if message is not None:
        return message

    body.pop("response_format", None)
    body.pop("temperature", None)
    message = _post_azure(url, body)
    if message is None:
        raise RuntimeError("Azure OpenAI rejected the chat completion")
    return message


def _post_azure(url: str, body: dict) -> dict | None:
    """POST one completion. None means the body should be retried without extras."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "api-key": os.environ["AZURE_OPENAI_API_KEY"],
        },
    )
    for attempt in range(DNS_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            if exc.code == 400 and ("response_format" in body or "temperature" in body):
                return None
            raise RuntimeError(f"Azure OpenAI answered {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            # A failed name lookup never reached Azure, so retrying is safe.
            if isinstance(exc.reason, socket.gaierror) and attempt < DNS_ATTEMPTS - 1:
                time.sleep(2)
                continue
            raise RuntimeError(f"Azure OpenAI could not be reached: {exc.reason}") from exc

    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Azure OpenAI did not return a chat completion") from exc
    if not isinstance(message, dict):
        raise RuntimeError("Azure OpenAI did not return a chat completion")
    return message
