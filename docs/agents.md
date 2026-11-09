# Connect an agent

An agent is an HTTP server that accepts `POST {base}/chat/completions` and returns an OpenAI chat completion. Pass `base`, the part before `/chat/completions`, when you start MedDataOS:

```bash
pixi run serve /path/to/folder --agent-url http://127.0.0.1:8001/v1
```

The server will not start without `--agent-url`. For each question it sends the chat, runs any tool calls on the open folder, and checks the answer before the page shows it.

## What the server sends

Each request is JSON:

| Field | Value |
|---|---|
| `model` | `AGENT_MODEL` from `.env`. Empty when that variable is unset. |
| `messages` | The system message, then the session history. |
| `tools` | The datactrl tools, omitted on the retry described below. |

`AGENT_API_KEY`, when set, is sent as `Authorization: Bearer …`. `AGENT_TIMEOUT` is how many seconds the server waits for each response. The default is `120`.

If the response has `tool_calls`, the server runs them on the open case and sends the results back as `tool` messages, up to sixteen rounds. The patient-card request also allows sixteen rounds. When a response has no tool calls, its content is the answer. A markdown code fence around JSON is removed.

If the citations are wrong, the server sends the agent's answer back with the reason and asks for a corrected one. After six corrections, or if the agent errors or times out, the page shows a short failure message instead of waiting.

The system message for a question contains:

- instructions to read the files with the tools and to ground the answer in them,
- the citation rule and a JSON example,
- `Case resources:` followed by a JSON list of discovered files.

Each resource in that list has `id`, `modality` (`note`, `structured`, or `dicom`), `label`, and `web_path`. `web_path` is the file's URL on this server, such as `/case/clinic_note.txt`. Paths are URL-encoded per segment. The list is the `resources` array from the discovery report.

The tools are `discover`, `describe`, `fetch`, `links`, `assert_link`, `dicom_tree`, and `dicom_groups`. Their schemas come from datactrl. `root` and `case_id` are removed from every schema, including `required`. The server drops those two arguments if the agent sends them, and sets `root` to the folder it opened before it runs the tool.

A tool result comes back as a `tool` message whose content is JSON:

```json
{"status": "ok", "name": "fetch", "result": {}}
```

A tool that raises, or arguments that are not a JSON object, come back as `{"status": "error", "name": "…", "message": "…"}` so the agent can try again. The server does not stop the question for that.

The server calls the agent again with those tool messages, up to sixteen completions. If the sixteenth completion still contains `tool_calls`, the page shows `The agent failed: no answer after 16 steps`.

If the endpoint answers `400` or `422` to a request that includes `tools`, the server retries that request once without `tools` and does not send tools again for the rest of that question. The agent can then answer only from the messages it has already been given.

When a completion has no `tool_calls`, its `content` is the answer. The server removes one markdown fence: a leading ` ``` ` line and a trailing ` ``` `. If the remaining text is a JSON object whose `citations` field is missing or empty, and `message`, `response`, or `text` is a non-empty string, that string replaces the object. An object that has citations is left as JSON for the check below.

## Patient card

When the server starts, it sends a separate completion. The system message asks for one JSON object and includes the same case resource list. The user message is `Fill in the patient card.`

The object may contain:

| Key | Kept when |
|---|---|
| `name`, `age`, `sex` | A string or number. Numbers are stored as text. |
| `blood_type` | Same. A blank value is stored as empty. |
| `allergies`, `conditions` | A list. Only non-empty strings are kept. |
| `data_dates` | An object whose values are `YYYY-MM-DD`. Other values are dropped. |

A markdown fence around that JSON is removed. Any other shape, invalid JSON, or a failed request leaves the card as the folder name. The sidebar already shows that name, and the server pushes the filled card to open pages when the reply is usable. Notes, Tables, and DICOM on the card come from the discovery report. `data_dates` is shown beside a citation when the cited path is `/case/<folder>/…` and `<folder>` is a key in `data_dates`.

## More than one agent

`--agent-url` stays the router: the only agent that talks to the page. Specialists are other chat endpoints the router can call. Register them in a TOML file:

```toml
[notes]
url = "http://127.0.0.1:8002/v1"
description = "Answers from clinical notes with verified quotes, dates, and conflicts."

[imaging]
url = "http://127.0.0.1:8003/v1"
description = "Looks at one DICOM slice. Use this for questions about the images, scans, contours, or what is visible on imaging."
```

```bash
pixi run serve /path/to/folder --agent-url http://127.0.0.1:8001/v1 --agents configs/agents.toml
```

`--specialist notes=http://127.0.0.1:8002/v1` does the same for one agent, and can be repeated. A name is a short lowercase word. The same name cannot be listed twice.

The router is given one extra tool per specialist, `consult_notes`, `consult_imaging`, and so on. The description is the only routing hint. The server runs that call: it posts the question and the datactrl tools to the specialist, and does not give the specialist a `consult_` tool, so agents cannot call each other. Each specialist is called at most once per question; a second call returns the first result. A timeout, an HTTP error, or citations that still fail after six corrections become a tool error. The router can still answer from the specialists that succeeded.

A specialist may answer in plain text, or with the citation JSON below. A `describe` or `fetch` it calls comes back with a `cite` token, and that token is what the citation names. A specialist that reads the case itself, without those tools, cites the file's `web_path` instead. Files it cites count as opened, so the router's own reply has to cite them too. With no specialists registered, none of this is added and the server talks only to `--agent-url`.

The router has to repeat a specialist's citation in its own reply, and the answer schema has no room for a slice preview, quote offsets, or a span link. So the server keeps each accepted specialist citation, and before the page sees the reply it puts the specialist's `agent`, DICOM slice (a `preview` of `slice_index`, `window`, and `overlay` becomes the same `dicom` record a fetched slice gets), checked `evidence`, and `conflicts` back on the router's citation for the same file. A router quote that matches none of the specialist's quotes is dropped, because the server cannot check it. Any citation that still names no agent is given the one for its file: `clinical_notes`, `imaging`, or `structured`.

## Clinical notes specialist

The notes specialist is `pixi run notes --case /path/to/case` from the root of this repo (it runs `python -m meddataos.specialists.notes.serve`). `pixi run stack` starts it with the rest. It prints an address such as `http://127.0.0.1:8002/v1`. For notes alone, pass that address as `--agent-url`. When more than one specialist is running, keep a router as `--agent-url` and register the notes process beside it:

```toml
[notes]
url = "http://127.0.0.1:8002/v1"
description = "Answers from clinical notes with verified quotes, dates, and conflicts. Use this for questions about the chart, history, labs in notes, and discrepancies between notes."
```

It opens that case itself and returns citation JSON. Each citation is tagged `clinical_notes` and carries the verified quotes and documented discrepancies, which the page shows on the badge, the hover card, and the source viewer. It does not ask the server to read files.

## Imaging specialist (stand-in)

A temporary imaging specialist, `pixi run imaging --case /path/to/case` from the root of this repo, stands in until a fuller imaging agent exists. Both specialists read `GEMINI_API_KEY` from this repo's `.env`. It prints `http://127.0.0.1:8003/v1`. Register it next to notes:

```toml
[imaging]
url = "http://127.0.0.1:8003/v1"
description = "Looks at one DICOM slice. Use this for questions about the images, scans, contours, or what is visible on imaging."
```

It ranks the case's series against the question, renders one preview slice (with contours for an RTSTRUCT or when the question asks for them), and describes that slice with a vision model (Gemini). A confident pick becomes one citation for the series file, tagged `imaging`, with a `preview` of the slice index, window, and overlay; the page loads that slice from `/api/dicom/preview`. If no series ranks confidently, the reply is plain text listing the candidates and has no citation. Any agent can take its place as long as it answers the same way.

## Azure OpenAI

The example router speaks Azure when these are set in this repo's `.env`. The notes and imaging specialists read the same variables from the same file:

```bash
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-10-21
```

`AZURE_OPENAI_DEPLOYMENT` is the deployment name. `AZURE_OPENAI_API_VERSION` is the date Azure puts on the request. When the key, endpoint, and deployment are set, those calls do not use Gemini. When they are empty, the specialists keep using `GEMINI_API_KEY`.

Some reasoning models reject function tools on chat completions unless `reasoning_effort` is `none`, and the page then gets no tools. Set `AZURE_OPENAI_REASONING_EFFORT=none` for those (`OPENAI_REASONING_EFFORT` when not using Azure). Leave it unset for models that don't take the parameter.

## Citations

`describe` and `fetch` record the resource they were called with, when that id is in the case file list. Those are the opened files. Other tools do not open a file. A failed call does not either.

If no file was opened, the answer is shown when it is plain text and contains neither `[cite:` nor `"citations"`. A JSON object in that case is refused with a request for plain text. Text that does contain a citation marker is checked with the rules below, against every discovered file.

If a file was opened, the whole answer must be one JSON object that matches `CitedAnswer` in `src/meddataos/server/answer.py`:

```json
{
  "response": "The planning CT shows the larynx [cite:c1]. The contours outline it [cite:c2]. Treatment finished on February 13 [cite:c3]. The dose was 51 Gy in 20 fractions [cite:c3].",
  "citations": [
    {
      "kind": "imaging",
      "cite": "c1",
      "summary": "Axial planning CT of the neck. The larynx is included on the displayed slice."
    },
    {
      "kind": "imaging",
      "cite": "c2",
      "summary": "RTSTRUCT for that planning CT. The larynx contour is named and outlined on the same slice.",
      "fields": ["roi_names"]
    },
    {
      "kind": "note",
      "cite": "c3",
      "agent": "clinical_notes",
      "summary": "Radiation oncology completion note dated 13 February. External-beam treatment finished that day, 51 Gy in 20 fractions, with follow-up arranged in radiation oncology.",
      "evidence": [
        {
          "n": 1,
          "claim": "Treatment finished on February 13",
          "quote": "Treatment completed February 13"
        },
        {
          "n": 2,
          "claim": "The prescribed dose was 51 Gy in 20 fractions",
          "quote": "51 Gy in 20 fractions"
        }
      ],
      "conflicts": [
        {
          "attribute": "rt.end_date",
          "severity": "high",
          "rationale": "The completion note and the follow-up note give different end dates.",
          "values": [
            {"value": "February 13", "note_label": "rt-completion", "start": 120, "end": 151},
            {"value": "February 20", "note_label": "follow-up", "note_id": "note:followup", "start": 40, "end": 51}
          ]
        }
      ]
    }
  ]
}
```

Each citation has a `kind`, and the kind follows from the call its token came from: `imaging` for a DICOM series, `note` for a clinical note, `table` for a table, and `file` for a path cited without a token. An imaging citation has only `cite`, `summary`, and `fields`. A finding from a note is a separate note citation, with the token from that note's own fetch. When the claim is a calculation or prediction from a call (for example a structure volume from a volume fetch), use `kind` `derived` with that call's cite token, a plain-language `method`, a `summary`, and optional `result` (`value` / `unit`), `detail`, and `inputs`. The server refuses an imaging citation that carries `evidence`, `agent`, or `conflicts`, and any citation whose kind does not match its call (except `derived`, which is allowed on any cite token). When `kind` is missing, the server uses the kind of the call.

The system message includes the JSON schema of `CitedAnswer`, with its descriptions and examples. After the first `describe` or `fetch` in a question, the router's requests also send a strict copy of that schema as `response_format` (`type: json_schema`, `strict: true`), so a model that supports structured outputs replies in this shape. If the endpoint answers 400 or 422, the server retries that conversation without `response_format`, and then without tools. The schema checks the shape. The server still checks the references: the token is a call from this question, each quote is in the note, and where the markers sit.

Put `[cite:token]` right after the words that call supports. A sentence may cite several calls, but the markers cannot sit side by side or be grouped at the end of the answer. `cite` is the token on the `describe` or `fetch` result, and the marker uses that same token. The server fills in `id`, `file`, `web_path`, and the command before the page sees the reply. The summary is two or three sentences of what that call shows: the finding, the date, and the measurement, so a reviewer can check the card without opening the file. A DICOM metadata citation may include `fields`, the metadata keys that support the claim. The values stay on the server. A `derived` citation's `method` is one or two sentences of how the value was obtained (input call, ROI or series, resampling or model, and the arithmetic or prediction step), readable without opening code. Read a note with `fetch` `view=text`. A citation of that call must include `evidence` with `quote`, a contiguous passage copied from the `text` that fetch returned. Several claims from one fetch are several evidence items on that one citation, each with its own `quote` from that same text, and the same `[cite:token]` goes after each of those claims. The server finds each passage, sets `start` and `end`, and fills `span_url`. It refuses a quote that is not in the note, and it refuses a quote that is the whole note. When notes disagree, the citation also sends `conflicts`. A specialist that did not call those tools cites `web_path` instead, with an `id` such as `1`, and that path must be a file in the open case. It may send `span_url` itself.

A refused answer is appended to the conversation, followed by a user message that starts with `The server refused that answer.`, states the problem, repeats the rule and the example, and lists the opened `web_path` values. The server does this at most six times after the original answer. The next failure is shown on the page as `The agent could not produce an answer with valid citations. Last problem: …`.

Anything other than a chat completion (`choices[0].message` as an object), a connection error, or a timeout is shown as `The agent failed: …`.

## The example agent

`pixi run agent` runs `examples/agent.py`. It listens on `127.0.0.1:8001` unless you pass `--host` and `--port`, and it accepts only `POST /v1/chat/completions`.

It replaces `model` with `OPENAI_MODEL` and posts `messages`, plus `tools` and `response_format` when the request includes them, to `OPENAI_BASE_URL`. When `OPENAI_BASE_URL` is unset it uses `https://api.openai.com/v1`. `OPENAI_API_KEY` is sent as a bearer token when set. The example agent's own wait is 120 seconds. `AGENT_MODEL`, `AGENT_API_KEY`, and `AGENT_TIMEOUT` apply to the MedDataOS server's call, which this forwarder does not read.

Set `OPENAI_MODEL`, or `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOYMENT`. Otherwise the example agent exits. Point `--agent-url` at another endpoint when you do not want this forwarder.
