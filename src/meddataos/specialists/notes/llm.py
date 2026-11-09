"""Model wrappers for the notes agent (single seam for tests to patch).

Gemini is the default. When AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and
AZURE_OPENAI_DEPLOYMENT are set, chat completions go to that Azure deployment
instead. AZURE_OPENAI_API_VERSION is the date in the query string
(default 2024-10-21).
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from meddataos.specialists.azure import azure_chat as _azure_chat
from meddataos.specialists.azure import azure_configured

_CLIENT = None
_CLIENT_LOCK = threading.Lock()


def client():
    """Shared Gemini client (created lazily)."""
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            from meddataos.specialists.gemini import create_client

            _CLIENT = create_client()
        return _CLIENT


def _config(schema: Any = None, json_mode: bool = False, system: str | None = None):
    from google.genai import types

    kwargs: dict[str, Any] = {"temperature": 0.0}
    if system:
        kwargs["system_instruction"] = system
    if schema is not None or json_mode:
        kwargs["response_mime_type"] = "application/json"
    if schema is not None:
        kwargs["response_schema"] = schema
    return types.GenerateContentConfig(**kwargs)


def _generate(model: str, contents: Any, config: Any, retries: int = 2):
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return client().models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 - network/API errors are retried
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Gemini call failed after {retries + 1} attempts: {last}")


def generate_json(
    prompt: str | list,
    *,
    model: str,
    schema: Any = None,
    system: str | None = None,
) -> Any:
    """Run a JSON-mode generation and return the parsed payload."""
    if azure_configured():
        extra = system or ""
        if schema is not None and hasattr(schema, "model_json_schema"):
            extra = (extra + "\n" if extra else "") + (
                "Return JSON matching this schema:\n"
                + json.dumps(schema.model_json_schema())
            )
        message = _azure_chat(_as_messages(prompt, extra or None), json_mode=True)
        return parse_json(message.get("content") or "")

    response = _generate(model, prompt, _config(schema, json_mode=True, system=system))
    return parse_json(response.text or "")


def generate_text(prompt: str | list, *, model: str, system: str | None = None) -> str:
    """Run a plain text generation."""
    if azure_configured():
        message = _azure_chat(_as_messages(prompt, system), json_mode=False)
        return (message.get("content") or "").strip()

    response = _generate(model, prompt, _config(system=system))
    return (response.text or "").strip()


def generate_with_tools(model: str, contents: list, tool, system: str):
    """One tool-enabled turn; returns the raw response for the caller's loop."""
    if azure_configured():
        message = _azure_chat(
            _as_messages(contents, system),
            tools=_openai_tools(tool),
            json_mode=False,
        )
        return _as_gemini_response(message)

    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=0.0, tools=[tool], system_instruction=system
    )
    return _generate(model, contents, config)


def _as_messages(prompt: Any, system: str | None) -> list[dict]:
    """Turn a string, a part list, or Gemini contents into chat messages."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})

    if isinstance(prompt, str):
        messages.append({"role": "user", "content": prompt})
        return messages

    if not isinstance(prompt, list):
        messages.append({"role": "user", "content": str(prompt)})
        return messages

    if prompt and not hasattr(prompt[0], "parts"):
        if any(getattr(part, "inline_data", None) for part in prompt):
            raise RuntimeError(
                "Scanned-PDF OCR is sent to Gemini. Unset the Azure variables "
                "or leave those pages for a Gemini run."
            )
        text = "\n".join(getattr(part, "text", None) or str(part) for part in prompt)
        messages.append({"role": "user", "content": text})
        return messages

    pending_ids: list[str] = []
    for index, content in enumerate(prompt):
        parts = list(getattr(content, "parts", None) or [])
        responses = [part for part in parts if getattr(part, "function_response", None)]
        if responses:
            for offset, part in enumerate(responses):
                call_id = pending_ids[offset] if offset < len(pending_ids) else f"call_{index}_{offset}"
                payload = getattr(part.function_response, "response", {}) or {}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(payload, default=str),
                })
            pending_ids = []
            continue

        calls = [
            part for part in parts
            if getattr(getattr(part, "function_call", None), "name", None)
        ]
        if calls:
            tool_calls = []
            pending_ids = []
            for offset, part in enumerate(calls):
                call_id = f"call_{index}_{offset}"
                pending_ids.append(call_id)
                args = part.function_call.args or {}
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": part.function_call.name,
                        "arguments": json.dumps(dict(args), default=str),
                    },
                })
            text = "".join(getattr(part, "text", None) or "" for part in parts)
            messages.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": tool_calls,
            })
            continue

        text = "".join(getattr(part, "text", None) or "" for part in parts)
        role = getattr(content, "role", "user")
        messages.append({
            "role": "assistant" if role in {"model", "assistant"} else "user",
            "content": text,
        })
    return messages


def _openai_tools(tool: Any) -> list[dict]:
    specs = []
    for decl in getattr(tool, "function_declarations", None) or []:
        if isinstance(decl, dict):
            function = decl
        else:
            params = getattr(decl, "parameters", None)
            if hasattr(params, "model_dump"):
                params = params.model_dump(exclude_none=True)
            elif not isinstance(params, dict):
                params = {"type": "object", "properties": {}}
            function = {
                "name": decl.name,
                "description": getattr(decl, "description", "") or "",
                "parameters": params or {"type": "object", "properties": {}},
            }
        specs.append({"type": "function", "function": function})
    return specs


class _FunctionCall:
    def __init__(self, name: str, args: dict) -> None:
        self.name = name
        self.args = args


class _Part:
    def __init__(self, text: str | None = None, function_call: _FunctionCall | None = None) -> None:
        self.text = text
        self.function_call = function_call


class _Content:
    def __init__(self, role: str, parts: list) -> None:
        self.role = role
        self.parts = parts


class _Candidate:
    def __init__(self, content: _Content) -> None:
        self.content = content


class _GeminiShape:
    """Enough of a Gemini response for the navigate loop to keep working."""

    def __init__(self, content: _Content) -> None:
        self.candidates = [_Candidate(content)]


def _as_gemini_response(message: dict) -> _GeminiShape:
    parts: list[_Part] = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        try:
            args = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        parts.append(_Part(function_call=_FunctionCall(function.get("name") or "", args)))
    if not parts:
        parts.append(_Part(text=message.get("content") or ""))
    return _GeminiShape(_Content("model", parts))


def parse_json(text: str) -> Any:
    """Parse JSON from model text, tolerating code fences and leading prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Model did not return JSON: {text[:200]!r}")
