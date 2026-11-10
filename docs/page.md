# Page

The page in `web/` is served by `src/meddataos/server`. Start it as [Start](index.md) describes. The page is the URL printed at startup, with `?patient=` set to the folder name. Optional specialists are registered with `--agents` or `--specialist`; see [Connect an agent](agents.md).

`HOST` and `PORT` in `.env` bind the server. The defaults are `127.0.0.1` and `8080`. When `HOST` is `0.0.0.0` or `::`, the printed URL still uses `127.0.0.1`.

## Sidebar

`GET /api/patients` returns the open folder. Its id and, until the agent answers, its name are the folder name. The startup request in [Connect an agent](agents.md) can replace the name, age, sex, blood type, allergies, and conditions. Hovering the name shows that card, plus Notes, Tables, or DICOM when the discovery report contains those files.

The folder's files are served at `/case/…`. A citation's `web_path` points there.

Conversations under the patient are the chat sessions for that folder name. `+ New` creates an empty one. The label is the first 60 characters of the first question, or `New conversation`. Sessions, pins, review checklists, and audit runs live in SQLite at `data/cases/<hash>/store.db` for the opened folder path, so a restart of the same case restores them. A question that was still running when the process stopped comes back idle; its history stays. A legacy `store.json` in that folder is imported once on startup. [Case data](data.md) describes that file.

## Chat

The box posts `message`, and the current `session_id` and `patient_id` when it has them, to `POST /api/chat`. Send stays disabled until the WebSocket is open, the box has text, and the current session is idle. Enter sends; Shift+Enter inserts a line.

| Message | When |
|---|---|
| `assistant` | The accepted answer, with `steps` and `duration_ms`. |
| `step` | A tool (`kind: tool`) or specialist call (`kind: consult`) started, finished, or failed. |
| `status` | What the question is waiting on between steps. |
| `patient` | The patient card, once the startup request fills it in. |

A step has `step_id`, `status` (`started`, `done`, or `error`), a short `label`, `started_ms`, and once it ends `duration_ms`. A finished `describe` or `fetch` also carries `cite` and `cite_kind` (`note`, `imaging`, `table`, or `derived` when the answer uses that token as a derived citation). A derived step also carries `sources`, each one the input cite token and what was taken from that call. The label names the file or the specialist. It does not include file contents, tool arguments, or the correction prompt. Status labels are `Thinking`, `Waiting for <name>`, `Checking citations`, and `Revising the answer`. Every step and status message carries `elapsed_ms`.

The waiting bubble has a thin moving bar along its top, a spinner, the current activity, and a running timer. The activity is the step in progress, such as `Reading clinic_note.txt`. While the agent is deciding or writing, with no tool in progress, the activity stays one line: `Thinking`, `Waiting for <name>`, or `Revising the answer`. That stretch is not added to the list. Below that are a count of files read and one row per step: a spinner, check, or cross; the action; the file name without its extension; the cite token and its type, such as `c1 · Note`; and how long it took when that was at least a tenth of a second. The finished answer collapses to `Worked for 14s · 4 files read`. An answer with no steps that took at least a second shows `Thought for 3s`.

`GET /api/session/{id}` returns `steps`, `activity`, and `elapsed_ms` while the question is running, and the steps and `duration_ms` on the assistant history entry once it is delivered. The patient-card request sends no steps. The page also reads that route on reconnect and every few seconds while it is waiting. A second question in a session that is already waiting returns an error and is not sent to the agent.

An assistant message that is JSON with `response` and a non-empty `citations` list is rendered from `response`. Each `[cite:id]` becomes a marker with the source label and a small token in the same box, such as `Notes c1`. Hovering it previews the file at `web_path`: png, jpg, jpeg, and svg as an image, mp4 as video, wav as audio, csv as a table, and anything else as text. Opening the marker shows that file and the citation summary. A summary that splits into two or more pieces of at least 20 characters, on a period or a newline, becomes a checkbox list of up to eight boxes. Checked boxes are stored with `PATCH /api/patients/{id}/reviews`, under the citation's web path.

Other assistant text is shown as markdown. `Clear` drops the selection on the page. The session remains on the server.

**Export audit** downloads the current conversation's audit runs as `audit-<patient>-<session>-<time>.json`. The same JSON is `GET /api/session/{id}/audit`. `GET /api/patients/{id}/audit` returns runs for that patient across chats.

The paperclip accepts `.csv` and `.xlsx`. The server writes the bytes to `data/input/dataset.csv` or `data/input/dataset.xlsx`, replacing the previous upload, and appends `[Uploaded file: <name>]` to the question. The agent sees that line. The file stays out of the case folder, so the datactrl tools do not list it. `data/` is gitignored.

## Pins

The pin control on a citation, or a selection inside an assistant message, posts to `/api/patients/{id}/pins`. A citation pin stores the citation, the question text, and the session id. A text pin stores the selected text and the session id. Pinning the same citation web path, or the same text, again returns the existing pin.

The right-hand panel lists pins for the open patient. Unpinning deletes that pin. A note and the tags `#follow-up`, `#critical`, `#reviewed`, `#discuss`, and `#normal` are saved on a citation pin with `PATCH`. Choosing a pin scrolls the source session to that citation or text.
