# Notes specialist

The notes specialist answers from clinical notes with verified quotes, dates, and conflicts. The router calls it as `consult_notes`. It does not ask the MedDataOS server to read files. It opens the case itself and returns citation JSON tagged `clinical_notes`.

Start it on the same case as the server:

```bash
pixi run notes --case /path/to/case
```

It prints an address such as `http://127.0.0.1:8002/v1`. `pixi run stack` starts it with the router and the imaging specialist. Register it in `configs/agents.toml`:

```toml
[notes]
url = "http://127.0.0.1:8002/v1"
description = "Answers from clinical notes with verified quotes, dates, and conflicts. Use this for questions about the chart, history, labs in notes, and discrepancies between notes."
```

For notes alone, pass that address as `--agent-url`. When a router is `--agent-url`, the server offers `consult_notes`, calls this process at most once per question, and still checks the router's citations.

The page shows the verified quotes and documented discrepancies on the badge, the hover card, and the source viewer. How the server copies those fields onto the router's reply is in [Connect an agent](../agents.md#clinical-notes-specialist).

It reads `GEMINI_API_KEY`, or the Azure settings, from `.env`. Scanned-PDF OCR uses Gemini only.
