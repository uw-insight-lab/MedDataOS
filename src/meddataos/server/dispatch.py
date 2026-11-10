"""Hold the conversation with the agent at --agent-url for each question.

The agent is any OpenAI-compatible chat completions endpoint: a plain model,
or an agent served behind that API. Tool calls it makes are run here on the
open case, its answer is sent back for correction until the citations pass,
and the accepted answer is pushed to every open page. At startup the agent
also fills in the patient card from the files.

"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from meddataos.server import answer
from meddataos.server.case import Answer, Contract, Profile, case, path_key
from meddataos.server.registry import Specialist
from meddataos.server import store
from meddataos.server.state import log, short_session, state

_tasks: set[asyncio.Task] = set()


def _background(coroutine) -> None:
    task = asyncio.create_task(coroutine)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


_TOOL_LABELS = {
    "discover": "Discovering the case",
    "describe": "Describing",
    "fetch": "Reading",
    "links": "Listing links",
    "assert_link": "Checking a link",
    "dicom_tree": "Reading the DICOM tree",
    "dicom_groups": "Grouping DICOM series",
}


def _file_label(arguments: dict) -> str:
    """The case file's label for a resource id, without reading the file."""
    resource_id = arguments.get("resource_id")

    if not isinstance(resource_id, str):
        return ""

    for item in case.files():
        if item.get("id") != resource_id:
            continue

        label = item.get("label")

        if isinstance(label, str) and label.strip():
            return label.strip()

        path = item.get("web_path") or ""
        return str(path).rsplit("/", 1)[-1]

    return ""


def _tool_label(name: str, arguments: dict) -> str:
    action = _TOOL_LABELS.get(name, name or "Running a tool")
    target = _file_label(arguments)

    if target and name in ("describe", "fetch"):
        return f"{action} {target}"

    return action


def _cite_kind(modality: str) -> str:
    """The citation type a finished read stands for, from the file's modality."""
    return {"dicom": "imaging", "note": "note", "structured": "table"}.get(modality, "")


def _stamp_answer_kinds(steps: list[dict], message: str) -> None:
    """Use the delivered citation's kind when the answer names one for that token."""
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return

    citations = parsed.get("citations") if isinstance(parsed, dict) else None

    if not isinstance(citations, list):
        return

    kinds = {}
    sources = {}

    for item in citations:
        if not isinstance(item, dict) or not isinstance(item.get("cite"), str):
            continue

        if isinstance(item.get("kind"), str) and item["kind"]:
            kinds[item["cite"]] = item["kind"]

        if item.get("kind") != "derived" or not isinstance(item.get("inputs"), list):
            continue

        used = []

        for entry in item["inputs"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("cite"), str):
                continue

            label = entry.get("label") if isinstance(entry.get("label"), str) else ""
            used.append(f"{entry['cite']} {label}".strip())

        if used:
            sources[item["cite"]] = used

    for step in steps:
        kind = kinds.get(step.get("cite"))

        if kind:
            step["cite_kind"] = kind

        used = sources.get(step.get("cite"))

        if used:
            step["sources"] = used


_step_started: dict[str, float] = {}


def _live(session_id: str):
    """The session while its question is open. The patient card and late replies have none."""
    if not session_id or session_id not in state.pending:
        return None

    return state.sessions.get(session_id)


async def record_step(session_id: str, step: dict) -> None:
    """Remember one step on the session and push it, with how long it took once it ends."""
    session = _live(session_id)

    if session is None:
        return

    step_id = step["step_id"]
    stored = next((item for item in session.steps if item["step_id"] == step_id), None)
    fields = {key: value for key, value in step.items() if value is not None}
    now = time.monotonic()

    if stored is None:
        stored = fields
        stored["started_ms"] = session.elapsed_ms()
        session.steps.append(stored)
        _step_started[step_id] = now
    else:
        stored.update(fields)

    if stored.get("status") in ("done", "error"):
        began = _step_started.pop(step_id, now)
        stored["duration_ms"] = int((now - began) * 1000)

    await state.hub.step(session_id, dict(stored), session.elapsed_ms())


async def set_status(session_id: str, label: str) -> None:
    """Say what the open question is waiting on, such as the model or the citation check."""
    session = _live(session_id)

    if session is None or session.status == label:
        return

    session.status = label
    await state.hub.status(session_id, label, session.elapsed_ms())


class AgentError(Exception):
    """The agent endpoint failed or returned something that is not a chat completion."""

    def __init__(self, message: str, status: int | None = None) -> None:
        """Remember the HTTP status when the endpoint returned one."""
        super().__init__(message)
        self.status = status


class AgentClient:
    """HTTP client for the OpenAI-compatible endpoint at --agent-url."""

    def __init__(self, url: str, model: str, key: str | None, timeout: float) -> None:
        """The completions URL, model name, optional key, and timeout."""
        self.url = url
        self.model = model
        self.key = key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> AgentClient:
        """Client from --agent-url and the AGENT_* environment variables."""
        return cls(
            state.agent_url or "",
            os.getenv("AGENT_MODEL", ""),
            os.getenv("AGENT_API_KEY"),
            float(os.getenv("AGENT_TIMEOUT", "120")),
        )

    def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        response_format: dict | None = None,
    ) -> dict:
        """One chat completions request. Returns the assistant message."""
        headers = {"Content-Type": "application/json"}

        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"

        body: dict = {"model": self.model, "messages": messages}

        if tools:
            body["tools"] = tools

        if response_format:
            body["response_format"] = response_format

        request = urllib.request.Request(
            f"{self.url}/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise AgentError(self._http_error(exc), exc.code) from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"could not reach {self.url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise AgentError(f"{self.url} did not return JSON") from exc

        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentError(f"{self.url} did not return a chat completion") from exc

        if not isinstance(message, dict):
            raise AgentError(f"{self.url} did not return a chat completion")

        return message

    def _http_error(self, exc: urllib.error.HTTPError) -> str:
        detail = ""

        try:
            body = json.loads(exc.read() or b"{}")
            error = body.get("error") if isinstance(body, dict) else None
            detail = (
                error.get("message", "")
                if isinstance(error, dict)
                else str(error or "")
            )
        except (OSError, json.JSONDecodeError):
            pass

        return f"{self.url} answered {exc.code}" + (f": {detail}" if detail else "")


class Conversation:
    """Messages exchanged with the agent for one piece of work, including tool calls."""

    MAX_STEPS = 16

    def __init__(
        self,
        messages: list[dict],
        session_id: str,
        client: AgentClient | None = None,
        tools: list[dict] | None = None,
        consult: bool = False,
        max_steps: int | None = None,
        answer_format: Callable[[], dict | None] | None = None,
        activity: str = "Thinking",
    ) -> None:
        """The messages so far, plus how tool calls and the answer format work."""
        self.messages = messages
        self.session_id = session_id
        self.client = client or AgentClient.from_env()
        self.tools = list(case.tools if tools is None else tools)
        self.consult = consult
        self.max_steps = self.MAX_STEPS if max_steps is None else max_steps
        self.answer_format = answer_format
        self.activity = activity

    async def reply(self) -> str:
        """Call the agent until it stops asking for tools, then return its text.

        Waiting on the model updates the live status. It does not add a row.
        """
        for _ in range(self.max_steps):
            await set_status(self.session_id, self.activity)
            message = await self._next()
            self.messages.append(message)
            calls = message.get("tool_calls") or []

            if not calls:
                return message.get("content") or ""

            for call in calls:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(await self._run_call(call)),
                    }
                )

        raise AgentError(f"no answer after {self.max_steps} steps")

    async def _next(self) -> dict:
        response_format = self.answer_format() if self.answer_format else None

        try:
            return await asyncio.to_thread(
                self.client.complete, self.messages, self.tools, response_format
            )
        except AgentError as exc:
            if exc.status not in (400, 422):
                raise

            if response_format:
                log("server", "agent refused the answer schema, retrying without it")
                self.answer_format = None
                return await self._next()

            if not self.tools:
                raise

        log("server", "agent refused the tool list, retrying without it")
        self.tools = []
        return await asyncio.to_thread(self.client.complete, self.messages, self.tools)

    async def _run_call(self, call: dict) -> dict:
        function = call.get("function") or {}
        name = function.get("name", "")

        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError as exc:
            await self._tool_step(name, {}, {"status": "error"})
            return {
                "status": "error",
                "name": name,
                "message": f"Arguments are not valid JSON: {exc}",
            }

        if not isinstance(arguments, dict):
            await self._tool_step(name, {}, {"status": "error"})
            return {
                "status": "error",
                "name": name,
                "message": "Arguments must be a JSON object",
            }

        if name.startswith("consult_"):
            return await self._consult(name, arguments)

        step_id = uuid4().hex[:12]
        await record_step(self.session_id, {
            "step_id": step_id,
            "kind": "tool",
            "status": "started",
            "label": _tool_label(name, arguments),
            "name": name,
        })
        result = await asyncio.to_thread(case.run, name, arguments, self.session_id)
        await self._finish_tool(step_id, name, arguments, result)
        return result

    async def _tool_step(self, name: str, arguments: dict, result: dict) -> None:
        """Record a tool call that failed before it ran."""
        step_id = uuid4().hex[:12]
        await record_step(self.session_id, {
            "step_id": step_id,
            "kind": "tool",
            "status": "started",
            "label": _tool_label(name, arguments),
            "name": name,
        })
        await self._finish_tool(step_id, name, arguments, result)

    async def _finish_tool(self, step_id: str, name: str, arguments: dict, result: dict) -> None:
        cite = result.get("cite") if isinstance(result, dict) else None
        label = _tool_label(name, arguments)

        if isinstance(cite, str):
            record = state.calls.get(self.session_id, {}).get(cite) or {}
            filename = record.get("file")

            if isinstance(filename, str) and filename and name in ("describe", "fetch"):
                verb = "Describing" if name == "describe" else "Reading"
                label = f"{verb} {filename}"

        step = {
            "step_id": step_id,
            "kind": "tool",
            "status": "error" if not isinstance(result, dict) or result.get("status") == "error" else "done",
            "label": label,
            "name": name,
        }

        if isinstance(cite, str):
            step["cite"] = cite
            cite_kind = _cite_kind(str(record.get("modality") or ""))

            if cite_kind:
                step["cite_kind"] = cite_kind

        await record_step(self.session_id, step)

    async def _consult(self, name: str, arguments: dict) -> dict:
        """Call one registered specialist. A second call returns the first result."""
        if not self.consult:
            return {
                "status": "error",
                "name": name,
                "message": "This agent cannot call another specialist.",
            }

        specialist_name = name.removeprefix("consult_")
        specialist = state.specialists.get(specialist_name)

        if specialist is None:
            return {
                "status": "error",
                "name": name,
                "message": f"Unknown specialist: {specialist_name}",
            }

        question = arguments.get("question")

        if not isinstance(question, str) or not question.strip():
            return {
                "status": "error",
                "name": name,
                "message": "question must be a non-empty string",
            }

        cache = state.consulted.setdefault(self.session_id, {})

        if specialist_name in cache:
            log(
                "agent",
                f"session={short_session(self.session_id)} "
                f"consult {specialist_name} already answered",
            )
            return cache[specialist_name]

        step_id = uuid4().hex[:12]
        await record_step(self.session_id, {
            "step_id": step_id,
            "kind": "consult",
            "status": "started",
            "label": f"Consulting {specialist_name}",
            "name": specialist_name,
        })
        result = await consult_specialist(specialist, question.strip(), self.session_id)
        cache[specialist_name] = result
        await record_step(self.session_id, {
            "step_id": step_id,
            "kind": "consult",
            "status": "error" if result.get("status") == "error" else "done",
            "label": f"Consulting {specialist_name}",
            "name": specialist_name,
        })
        return result


def router_tools() -> list[dict]:
    """Datactrl tools, plus one consult tool per registered specialist."""
    return [*case.tools, *(spec.tool() for spec in state.specialists.values())]


def _client_for(url: str) -> AgentClient:
    return AgentClient(
        url,
        os.getenv("AGENT_MODEL", ""),
        os.getenv("AGENT_API_KEY"),
        float(os.getenv("AGENT_TIMEOUT", "120")),
    )


def specialist_instructions() -> str:
    """Prompt for a specialist: cite case files, and do not call other agents."""
    return "\n".join(
        [
            "You are a specialist answering one question about one patient's medical "
            "files. "
            "Use the tools to read the files when you need them. "
            "Ground your answer in the files. "
            "Do not call another specialist.",
            f"Citation rule: {Contract.specialist_rule()}",
            f"Answer schema, with examples: {answer.prompt_schema()}",
            f"Case resources: {json.dumps(case.files())}",
        ]
    )


def _remember_citations(session_id: str, text: str) -> None:
    """Treat files named in an accepted specialist answer as opened for the router."""
    if session_id not in state.pending:
        return

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return

    citations = parsed.get("citations") if isinstance(parsed, dict) else None

    if not isinstance(citations, list):
        return

    known = {path_key(item["web_path"]): item for item in case.files()}
    opened = state.reads.setdefault(session_id, [])
    seen = {path_key(item.get("web_path")) for item in opened}
    calls = state.calls.get(session_id, {})
    fetched = {path_key(call.get("web_path")) for call in calls.values()}

    for citation in citations:
        if not isinstance(citation, dict) or citation.get("cite"):
            continue

        ref = known.get(path_key(citation.get("web_path")))
        key = path_key(ref.get("web_path")) if ref else ""

        if ref:
            _keep_specialist_fields(session_id, key, citation)

        if ref and key not in seen and key not in fetched:
            opened.append(ref)
            seen.add(key)


# ---------------------------------------------------------------------------
# What a specialist said about a file
#
# The router has to repeat a specialist's citation in its own reply, and the
# strict answer schema has no room for a slice preview, quote offsets, or a span
# link. The server keeps the specialist's checked citation and puts those fields
# back on whatever the router cites for the same file.
# ---------------------------------------------------------------------------


def _keep_specialist_fields(session_id: str, key: str, citation: dict) -> None:
    """Remember what an accepted specialist citation said about one file."""
    kept = state.cited.setdefault(session_id, {}).setdefault(
        key, {"evidence": [], "conflicts": []}
    )

    for field in ("agent", "summary"):
        value = citation.get(field)

        if isinstance(value, str) and value.strip() and not kept.get(field):
            kept[field] = value.strip()

    for field in ("preview", "dicom"):
        value = citation.get(field)

        if isinstance(value, dict) and value and not kept.get(field):
            kept[field] = value

    for item in citation.get("evidence") or []:
        if isinstance(item, dict) and item not in kept["evidence"]:
            kept["evidence"].append(item)

    conflicts = citation.get("conflicts")

    if isinstance(conflicts, list) and conflicts and not kept["conflicts"]:
        kept["conflicts"] = [item for item in conflicts if isinstance(item, dict)]


def _dicom_record(web_path: str, preview: object) -> dict | None:
    """DICOM slice record built from a specialist preview."""
    if not isinstance(preview, dict) or not web_path:
        return None

    entry: dict = {"web_path": web_path}

    for field in ("slice_index", "n_slices", "window", "roi"):
        if preview.get(field) is not None:
            entry[field] = preview[field]

    if preview.get("overlay"):
        entry["overlay"] = True

    return {"previews": [entry]}


def _same_quote(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False

    a, b = " ".join(left.lower().split()), " ".join(right.lower().split())
    return (
        bool(a)
        and bool(b)
        and (a == b or (min(len(a), len(b)) >= 12 and (a in b or b in a)))
    )


def _merge_evidence(sent: object, kept: list[dict]) -> list[dict]:
    """Replace router quotes with the specialist's checked copy of the same quote.

    A quote the specialist never gave is dropped: the server cannot check it, and the
    page shows quotes as verified. If none match, the specialist's own quotes are used.
    """
    merged: list[dict] = []

    for item in sent if isinstance(sent, list) else []:
        if not isinstance(item, dict):
            continue

        match = next(
            (row for row in kept if _same_quote(item.get("quote"), row.get("quote"))),
            None,
        )

        if match is None:
            continue

        fixed = dict(match)

        for field in ("n", "claim"):
            if item.get(field) is not None:
                fixed[field] = item[field]

        merged.append(fixed)

    return merged or [dict(row) for row in kept]


def _restore_specialist_fields(session_id: str, text: str) -> str:
    """Put specialist provenance back on the router's citations.

    Agent, DICOM slice, quotes, and discrepancies come from the specialist.
    """
    saved = state.cited.get(session_id) or {}

    if not saved:
        return text

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text

    citations = parsed.get("citations") if isinstance(parsed, dict) else None

    if not isinstance(citations, list):
        return text

    files = {path_key(item["web_path"]): item["web_path"] for item in case.files()}
    changed = False

    for item in citations:
        if not isinstance(item, dict) or item.get("cite"):
            continue

        key = path_key(item.get("web_path"))
        kept = saved.get(key)

        if not kept:
            continue

        if kept.get("agent") and not item.get("agent"):
            item["agent"] = kept["agent"]

        if kept.get("summary") and not str(item.get("summary") or "").strip():
            item["summary"] = kept["summary"]

        if not item.get("dicom"):
            stored = files.get(key)
            raw_path = item.get("web_path")
            cited_path = stored if isinstance(stored, str) else ""

            if not cited_path and isinstance(raw_path, str):
                cited_path = raw_path

            record = kept.get("dicom") or _dicom_record(cited_path, kept.get("preview"))

            if record:
                item["dicom"] = record

        if kept["evidence"]:
            item["evidence"] = _merge_evidence(item.get("evidence"), kept["evidence"])

        if kept["conflicts"]:
            item["conflicts"] = kept["conflicts"]

        changed = True

    return json.dumps(parsed, ensure_ascii=False) if changed else text


async def consult_specialist(
    specialist: Specialist, question: str, session_id: str
) -> dict:
    """Ask one specialist, then return its answer or a tool error. Never raises."""
    label = short_session(session_id)
    name = f"consult_{specialist.name}"
    log("server", f"session={label} consult {specialist.name}: {question}")
    conversation = Conversation(
        [
            {"role": "system", "content": specialist_instructions()},
            {"role": "user", "content": question},
        ],
        session_id,
        client=_client_for(specialist.url),
        tools=list(case.tools),
        consult=False,
        activity=f"Waiting for {specialist.name}",
    )
    problem = ""

    try:
        for attempt in range(1, Question.MAX_REVISIONS + 2):
            text = message_text(await conversation.reply())

            if not text.strip():
                problem = "The reply was empty."
                verdict = None
            else:
                verdict = Answer(
                    text, [], case.files(), state.calls.get(session_id, {})
                )
                problem = verdict.problem or ""

            if verdict is not None and verdict.problem is None:
                _remember_citations(session_id, text)
                log("agent", f"session={label} consult {specialist.name} ok")
                return {"status": "ok", "name": name, "result": text}

            log(
                "agent",
                f"session={label} consult {specialist.name} "
                f"reply {attempt} refused: {problem}",
            )
            correction = (
                verdict.correction()
                if verdict is not None
                else f"The server refused that answer. {problem}"
            )
            conversation.messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": correction},
            ]
    except Exception as exc:
        log("agent", f"session={label} consult {specialist.name} failed: {exc}")
        return {"status": "error", "name": name, "message": str(exc)}

    return {
        "status": "error",
        "name": name,
        "message": (
            f"The specialist could not produce valid citations. Last problem: {problem}"
        ),
    }


class Question:
    """One user question: ask, then send refused answers back until one passes."""

    MAX_REVISIONS = 6
    PROMPT = (
        "You answer questions about one patient's medical files. "
        "Use the tools to read the files before answering. "
        "Ground your answer in the files. "
        "If you open no files, reply to the user in plain text, not JSON. "
        "Otherwise the whole reply is one JSON object that follows the citation "
        "rule below, "
        "with no sentences before or after it."
    )

    def __init__(self, session_id: str) -> None:
        """The session this question belongs to."""
        self.session_id = session_id
        self.label = short_session(session_id)

    def start(self) -> None:
        """Mark the session busy and ask the agent in the background."""
        session = state.sessions[self.session_id]
        session.steps = []
        session.status = ""
        session.started = time.monotonic()
        state.pending.add(self.session_id)
        question = session.history[-1]["content"]
        state.runs[self.session_id] = {
            "run_id": uuid4().hex,
            "question": question,
            "started_at": datetime.now(UTC).isoformat(),
            "refusals": [],
        }
        log("server", f"session={self.label} question sent to the agent: {question}")
        _background(self.answer())

    async def answer(self) -> None:
        """Ask, then send refused answers back until one passes or retries run out."""
        history = state.sessions[self.session_id].history
        conversation = Conversation(
            [{"role": "system", "content": self._instructions()}]
            + [{"role": turn["role"], "content": turn["content"]} for turn in history],
            self.session_id,
            tools=router_tools(),
            consult=bool(state.specialists),
            answer_format=self._answer_format,
        )
        problem = ""

        try:
            for attempt in range(1, self.MAX_REVISIONS + 2):
                text = message_text(await conversation.reply())

                if self.session_id not in state.pending:
                    return

                await set_status(self.session_id, "Checking citations")
                opened = state.reads.get(self.session_id, [])
                verdict = Answer(
                    text, opened, case.files(), state.calls.get(self.session_id, {})
                )
                problem = verdict.problem or ""

                if verdict.problem is None:
                    await self._deliver(text)
                    return

                run = state.runs.get(self.session_id)

                if run is not None:
                    run["refusals"].append({"attempt": attempt, "problem": problem})

                log(
                    "agent",
                    f"session={self.label} reply {attempt}/{self.MAX_REVISIONS + 1} "
                    f"refused: {problem}",
                )
                log("agent", f"session={self.label} refused reply was: {text}")
                conversation.messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": verdict.correction()},
                ]
                conversation.activity = "Revising the answer"

            await self._deliver(
                "The agent could not produce an answer with valid citations. "
                f"Last problem: {problem}"
            )

        except Exception as exc:
            log("server", f"session={self.label} agent failed: {exc}")
            await self._deliver(f"The agent failed: {exc}")
        finally:
            state.consulted.pop(self.session_id, None)
            state.cited.pop(self.session_id, None)

    def _answer_format(self) -> dict | None:
        """The answer schema, once a describe or fetch means the reply must be cited."""
        return answer.response_format() if state.calls.get(self.session_id) else None

    def _instructions(self) -> str:
        lines = [
            self.PROMPT,
            f"Citation rule: {Contract.RULE}",
            f"Answer schema, with examples: {answer.prompt_schema()}",
            f"Case resources: {json.dumps(case.files())}",
        ]

        if state.specialists:
            roster = "; ".join(
                f"consult_{name}: {spec.description}"
                for name, spec in state.specialists.items()
            )
            lines.append(
                "Specialists: " + roster + ". "
                "Call consult_<name> with the part of the question that specialist "
                "answers. "
                "Call each specialist at most once. "
                "When a specialist returns citation JSON, copy those citations into "
                "your own reply. "
                "If a specialist returns an error, say so and answer from the others."
            )

        return "\n".join(lines)

    async def _deliver(self, message: str) -> None:
        """Record the answer once, stop waiting, and push it to every open page."""
        if self.session_id not in state.pending:
            return

        calls = state.calls.get(self.session_id, {})
        message = _restore_specialist_fields(self.session_id, message)
        message = case.expand_citations(message, calls)
        message = case.name_sources(message, calls)
        state.pending.discard(self.session_id)
        state.reads.pop(self.session_id, None)
        state.calls.pop(self.session_id, None)
        state.cited.pop(self.session_id, None)

        session = state.sessions[self.session_id]
        steps = [dict(item) for item in session.steps]
        _stamp_answer_kinds(steps, message)
        duration_ms = session.elapsed_ms()
        for item in session.steps:
            _step_started.pop(item["step_id"], None)
        session.steps = []
        session.status = ""
        session.started = None
        session.add("assistant", message, steps, duration_ms)
        session.processing = False

        run = state.runs.pop(self.session_id, None)

        if state.root is not None and run is not None:
            store.append_audit_run(
                state.root,
                {
                    **run,
                    "session_id": self.session_id,
                    "patient_id": session.patient_id,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "duration_ms": duration_ms,
                    "outcome": _audit_outcome(message),
                    "steps": steps,
                    "calls": store.calls_for_audit(calls),
                    "answer": message,
                    "citations": store.citations_for_audit(message),
                },
            )

        state.save()

        await state.hub.assistant(self.session_id, message, steps, duration_ms)
        log(
            "server",
            f"session={self.label} answer sent to "
            f"{len(state.hub.connections)} page(s): {self._preview(message)}",
        )

    @staticmethod
    def _preview(message: str) -> str:
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError:
            return message

        if isinstance(parsed, dict) and isinstance(parsed.get("response"), str):
            citations = parsed.get("citations")
            count = len(citations) if isinstance(citations, list) else 0
            return f"{count} citation(s): {parsed['response']}"

        return message


class PatientCard:
    """The startup request that asks the agent to fill in the sidebar card."""

    MAX_STEPS = 16
    PROMPT = (
        "You fill in the patient card for one patient's medical files. "
        "Use the tools to read the files. Do not guess: leave a field empty when "
        "the files do not say. "
        "Reply with only one JSON object with these keys: "
        '"name" (string), "age" (string, such as "64"), "sex" (string), '
        '"blood_type" (string, or null), "allergies" (list of strings), '
        '"conditions" (list of strings), and "data_dates" (object mapping each '
        "top-level folder of the case to the latest date in it, as YYYY-MM-DD)."
    )

    async def fill(self) -> None:
        """Ask the agent for the card and store whatever the files support."""
        conversation = Conversation(
            [
                {
                    "role": "system",
                    "content": (
                        f"{self.PROMPT}\nCase resources: {json.dumps(case.files())}"
                    ),
                },
                {"role": "user", "content": "Fill in the patient card."},
            ],
            "",
            max_steps=self.MAX_STEPS,
        )

        try:
            profile = Profile.from_agent(
                json.loads(_strip_fence(await conversation.reply()))
            )
        except Exception as exc:
            log("server", f"patient card not filled, showing the folder name: {exc}")
            return

        state.profile = profile.as_dict()
        filled = {key: value for key, value in state.profile.items() if value}
        summary = json.dumps(filled) if filled else "nothing found in the files"
        log("server", f"patient card filled: {summary}")

        card = case.patient()

        if card:
            await state.hub.broadcast({"type": "patient", "patient": card.as_dict()})


def _audit_outcome(message: str) -> str:
    if message.startswith("The agent could not") or message.startswith("The agent failed"):
        return "failure"
    return "success"


def ask(session_id: str) -> None:
    """Answer the latest question in this session in the background."""
    Question(session_id).start()


def fill_card() -> None:
    """Fill the patient card in the background and push it to the pages."""
    log("server", "asking the agent to fill in the patient card")
    _background(PatientCard().fill())


def _strip_fence(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[-1]

        if text.endswith("```"):
            text = text[: text.rfind("```")].strip()

    return text


def message_text(text: str) -> str:
    """Drop a markdown fence, and a JSON wrapper when the answer has no citations."""
    text = _strip_fence(text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text

    if not isinstance(parsed, dict) or parsed.get("citations"):
        return text

    for key in ("message", "response", "text"):
        value = parsed.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return text
