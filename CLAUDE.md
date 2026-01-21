# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MedDataOS is a multi-agent AI system for automated medical data analysis using Google's Gemini API. It orchestrates specialized agents through a tool-calling pattern where Gemini coordinates data preparation, analysis, and reporting agents.

## Running the Application

### Web Server (Primary Interface)
```bash
python web/backend/server.py
```
- Starts FastAPI server on `http://127.0.0.1:8080`
- WebSocket streaming at `ws://127.0.0.1:8080/ws`

### CLI Mode (Legacy)
```bash
python -m src.main
```
Uses `INITIAL_QUERY` from `src/agents/prompts.py`

### Environment Setup
Create `.env` file in project root:
```
GEMINI_API_KEY=your_api_key_here
```

## Core Architecture

### Tool-Calling Orchestration Pattern

The system uses Gemini's function calling to coordinate specialized agents. **Critical flow:**

1. **User Query → Orchestrator** (`src/core/orchestrator.py`)
   - Receives query + optional file upload
   - Creates `GenerateContentConfig` with tool definitions
   - Sends to Gemini 2.5 Flash with conversation history

2. **Tool Calling Loop**
   - Gemini returns `function_call` with tool name + arguments
   - Orchestrator maps tool name to agent config
   - Executes agent via `execute_agent(plan, agent_config)`
   - Attaches result as `function_response`
   - Loops until Gemini stops calling tools

3. **Agent Execution** (`src/agents/executors.py`)
   - Takes "plan" (instructions) from Gemini
   - Sends plan to Gemini with agent-specific system prompt
   - Gemini generates Python code
   - Code saved to `workspace/{agent_name}/generated_script.py`
   - Executed via subprocess
   - Summary generated and saved to `shared_knowledge.xml`

### Agent Types

| Agent | Tool Name | Input | Output Location |
|-------|-----------|-------|-----------------|
| **Preparation** | `prepare_data_for_analysis` | Raw CSV/Excel | `workspace/preparation/output_dataset.csv` |
| **Analysis** | `prepare_analysis` | Cleaned CSV | `workspace/analysis/model.joblib` |
| **Report** | `generate_analysis_report` | Model + data | `workspace/report/analysis_report.txt` |
| **Chest X-ray** | `classify_chest_xray` | Image URL | External API response |

**Key Pattern:** Each agent:
1. Receives a structured "plan" (not raw data)
2. Generates Python code dynamically based on plan
3. Executes code in isolated workspace
4. Outputs to predictable file location for next agent

### WebSocket Streaming Implementation

**Backend:** `web/backend/server.py`
- `WebSocketManager` class manages active connections
- Logging functions call `_broadcast_log()` which uses `asyncio.run_coroutine_threadsafe()` to cross thread boundary from orchestrator thread to async event loop

**Frontend:** `web/frontend/app.js`
- Message filtering logic:
  - `assistant` → Chat bubble only (stops processing flag)
  - `tool_call`/`tool_result` → Execution log entries
  - `user` → Skipped (already shown locally)

**Critical Detail:** Logs broadcast from background thread require `asyncio.run_coroutine_threadsafe()` to schedule in event loop safely.

### Session Management

**In-memory storage:** `sessions = {}`
- Structure: `{"history": [...], "processing": bool, "uploaded_file": str}`
- Session ID stored in frontend localStorage
- Survives page refresh but NOT server restart
- `processing` flag prevents concurrent requests per session

### File Upload Pipeline

1. User uploads CSV/Excel via `/api/chat` (multipart/form-data)
2. Backend validates extension: `.csv` or `.xlsx`
3. Saves to `data/input/{session_id}_{filename}`
4. Orchestrator modifies system instruction when file present:
   ```
   IMPORTANT: The user has uploaded a file at: {uploaded_file}
   You MUST call the prepare_data_for_analysis tool first...
   ```
5. Gemini sees file path and plans appropriate tool sequence

## Key Files & Their Roles

### Orchestration
- `src/core/orchestrator.py` - Main control loop, tool calling, conversation history management
- `src/core/gemini_client.py` - Gemini API client setup
- `src/tools/definitions.py` - Function declarations for Gemini tool calling

### Agent Implementation
- `src/agents/executors.py` - Code generation, execution, summarization
- `src/agents/prompts.py` - System prompts for each agent (defines library constraints)

### Web Interface
- `web/backend/server.py` - FastAPI server, session management, file uploads, WebSocket broadcasting
- `web/frontend/app.js` - WebSocket client, message filtering, markdown rendering
- `web/frontend/index.html` - UI structure
- `web/frontend/style.css` - Styling including markdown element styles

### Utilities
- `src/utils/logging.py` - WebSocket manager, XML persistence, log broadcasting functions

## Non-Obvious Implementation Details

### Thread Safety
- Orchestrator runs in background thread (`threading.Thread`)
- WebSocket broadcasts cross thread boundary via `asyncio.run_coroutine_threadsafe()`
- Session `processing` flag prevents race conditions

### Agent Library Constraints
Each agent has strict library limitations defined in system prompts:
- **Preparation:** pandas, numpy only
- **Analysis:** scikit-learn, joblib only
- **Report:** pandas, joblib, json only

**Why:** Ensures generated code is predictable and reduces security surface area

### Data Continuity Pattern
Agents don't pass data directly - they write/read from predictable file locations:
```
Preparation → workspace/preparation/output_dataset.csv
Analysis (reads above) → workspace/analysis/model.joblib
Report (reads both above) → workspace/report/analysis_report.txt
```

### Markdown Rendering
- Frontend loads `marked.js` and `DOMPurify` from CDN
- Only assistant messages rendered as markdown (security)
- User messages kept as escaped plain text
- Styling in `.message-content` scopes all markdown elements

### Code Cleanup Pattern
Generated Python code may include markdown code blocks:
```python
if python_code.startswith("```python"):
    python_code = python_code[len("```python"):].strip()
if python_code.endswith("```"):
    python_code = python_code[:-len("```")].strip()
```

## Common Modification Patterns

### Adding a New Agent
1. Create function declaration in `src/tools/definitions.py`
2. Add system prompt to `src/agents/prompts.py`
3. Add agent config mapping in `orchestrator.py`:
   ```python
   agent_configs = {
       "your_tool_name": {
           'system_prompt': YOUR_AGENT_SYSTEM_PROMPT,
           'agent_name': 'your_agent',
           'plan_key': 'plan'
       }
   }
   ```
4. Ensure workspace directory exists: `workspace/your_agent/`

### Modifying Agent Behavior
- Edit system prompts in `src/agents/prompts.py`
- Change allowed libraries
- Modify input/output location instructions
- Adjust code generation expectations

### Changing WebSocket Log Display
- Frontend filtering: `web/frontend/app.js` in `handleWebSocketMessage()`
- Backend broadcast control: `src/utils/logging.py` in log functions
- Message types: `user`, `assistant`, `tool_call`, `tool_result`, `system`

### Adjusting Session Behavior
- Timeout logic: Add expiry checking in `web/backend/server.py`
- History limits: Slice `session["history"]` before passing to orchestrator
- Concurrent handling: Modify `processing` flag logic

## Important Constraints

### Security
- Generated code executes with server process permissions
- No sandboxing of agent code execution
- File uploads saved without encryption
- DOMPurify sanitizes markdown to prevent XSS

### Limitations
- Single-user system (no authentication)
- Sessions not persistent across server restarts
- No parallel agent execution (sequential only)
- No automatic retry on agent failures

### API Dependencies
- Requires Google Gemini API key
- All agents use `gemini-2.5-pro` model
- Chest X-ray agent expects external service at `localhost:8000`

## Troubleshooting

### Port Already in Use
```bash
lsof -ti :8080 | xargs kill -9
```

### Agent Execution Failures
Check generated script: `workspace/{agent_name}/generated_script.py`
- Verify library imports
- Check file paths
- Review subprocess output in logs

### WebSocket Disconnects
- Check browser console for errors
- Verify server is running
- Clear browser cache (files have version query params)

### File Upload Issues
- Verify `python-multipart` installed
- Check file extension validation
- Ensure `data/input/` directory exists and is writable
- For Excel files, ensure `openpyxl` is installed
