# Case data

Chats, pins, review checklists, and audit runs for the opened folder are stored in SQLite. The path is `data/cases/<hash>/store.db`, where `<hash>` is the first 16 hex characters of the SHA-256 of the resolved case path. `data/` is gitignored. The database holds question text and answers, so treat it as patient data.

A leftover `store.json` in that folder is imported once, then renamed `store.json.bak`.

Restarting the server on the same folder restores the rows. A question that was still running comes back idle. Its history stays. Tool-call scratch state (`calls`, `reads`, `cited`) is memory only and is not restored.

## Tables

| Table | What it holds |
|---|---|
| `sessions` | One row per chat: patient id, message history, and the last uploaded file path. |
| `pins` | Citation and text pins, keyed by patient and pin id. |
| `reviews` | Checklist state, keyed by patient and citation path. |
| `audit_runs` | One row per finished question. Append-only. |
| `meta` | Schema version and the case path. |

Sessions, pins, and reviews are rewritten when the page changes them. Audit runs are inserted when an answer is delivered, including a failure message.

## Audit run

Each run stores the question, start and finish times, `duration_ms`, `outcome` (`success` or `failure`), the step list, tool calls, citation-check refusals, the delivered answer, and citation summaries.

A tool call in the export is the cite token, tool name, file label, modality, and `web_path`. A refusal is the attempt number and the problem string. A citation summary keeps `cite`, `id`, `kind`, `web_path`, `summary`, and `agent` when those fields are present.

The export leaves out file bodies, evidence quotes, and the correction prompt sent back to the agent.

## How to read it

In the chat panel, **Export audit** downloads the current conversation. While the server is running:

| Route | Returns |
|---|---|
| `GET /api/session/{session_id}/audit` | Runs for that chat, newest first. |
| `GET /api/patients/{patient_id}/audit` | Runs for that patient across chats. |

Both accept `limit` (default 100, maximum 500).

From the shell, the same rows are in `audit_runs`:

```bash
sqlite3 data/cases/<hash>/store.db \
  "SELECT run_id, outcome, started_at, question FROM audit_runs ORDER BY started_at DESC LIMIT 10;"
```
