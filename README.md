# MedDataOS - Medical Data Operating System

A multi-agent AI system for automated medical data analysis using Google's Gemini API. Features an interactive chat interface with file upload capabilities and specialized agents for data preparation, analysis, and reporting.

## Features

- **Interactive Chat Interface** - Web-based UI with real-time execution streaming
- **File Upload Support** - Upload CSV or Excel files for automated analysis
- **Multi-Agent Pipeline** - Specialized agents for preparation, analysis, and reporting
- **Session Management** - Persistent conversation history across page refreshes
- **Real-time Logs** - WebSocket streaming of agent execution details
- **Chest X-ray Classification** - External API integration for medical image analysis

## Architecture

The system uses a tool-calling orchestration pattern where Gemini API coordinates specialized agents:

```
User Query + File Upload
    ↓
Orchestrator (Gemini 2.5 Flash)
    ↓
┌──────────────────────────────────────┐
│  Preparation Agent                   │
│  - Cleans and validates data         │
│  - Outputs: cleaned CSV              │
└──────────┬───────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  Analysis Agent                      │
│  - Trains ML models                  │
│  - Outputs: trained model (.joblib)  │
└──────────┬───────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  Report Agent                        │
│  - Generates comprehensive report    │
│  - Outputs: analysis report (.txt)   │
└──────────────────────────────────────┘
```

Each agent generates Python code dynamically based on the task and executes it in isolated workspaces.

## Prerequisites

- Python 3.10 or higher
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))
- pip (Python package manager)

## Installation

### 1. Clone or Download the Repository

```bash
cd MedDataOS
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv

# Activate on macOS/Linux:
source venv/bin/activate

# Activate on Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- Core: `pandas`, `numpy`, `scikit-learn`, `joblib`
- AI: `google-genai`, `langgraph`, `langchain`
- Web: `fastapi`, `uvicorn`, `websockets`, `python-multipart`
- Utils: `python-dotenv`, `matplotlib`, `seaborn`, `openpyxl`

## Configuration

### 1. Create `.env` File

Create a file named `.env` in the project root:

```bash
GEMINI_API_KEY=your_api_key_here
```

Replace `your_api_key_here` with your actual Gemini API key.

### 2. Prepare Directories

The system creates these automatically, but you can set them up manually:

```bash
mkdir -p data/input
mkdir -p workspace/{preparation,analysis,report}
mkdir -p outputs
```

## Running the Application

### Start the Web Server

```bash
python web/backend/server.py
```

The server starts on `http://127.0.0.1:8080`

You should see:
```
🌐 Starting MedDataOS Web Monitor...
📡 WebSocket server: ws://127.0.0.1:8080/ws
🖥️  Web UI: http://127.0.0.1:8080
💡 Press Ctrl+C to stop (NOT Ctrl+Z)
```

### Access the Web Interface

Open your browser and navigate to:
```
http://127.0.0.1:8080
```

## Usage

### 1. Simple Chat Query

Type a message and press Send or Enter:
```
"Explain what kind of analysis can be performed on medical datasets"
```

### 2. File Upload + Analysis

1. Click the **📎 attach button**
2. Select a CSV or Excel file (`.csv` or `.xlsx` format)
3. Type your request:
   ```
   "Analyze this patient data and predict survival outcomes"
   ```
4. Click **Send**

The system will automatically:
- Save your uploaded file
- Run the **Preparation Agent** (clean and validate data)
- Run the **Analysis Agent** (train ML models)
- Run the **Report Agent** (generate insights and recommendations)
- Stream real-time logs showing each step
- Return a final comprehensive report

### 3. View Execution Details

The chat interface shows:
- **Chat bubbles** - Clean conversation with the system
- **Execution logs** - Detailed agent activity:
  - 🛠️ **Tool Call** - Agent invocation
  - 📦 **Tool Result** - Agent output summary

### 4. Clear Chat

Click the **Clear** button to:
- Reset conversation history
- Start a new session
- Remove any attached files

## Example Queries

### Data Analysis
```
"I have a CSV with patient demographics and lab results.
 Analyze it to predict diabetes risk."
```

### Report Generation
```
"Generate a summary report of the model performance
 with visualizations and recommendations."
```

### Chest X-ray Classification
```
"Classify this chest X-ray: https://example.com/xray.jpg"
```

## Project Structure

```
MedDataOS/
├── src/                        # Source code
│   ├── main.py                 # CLI entry point (legacy)
│   ├── core/                   # Core orchestration
│   │   ├── orchestrator.py     # Main agent coordinator
│   │   └── gemini_client.py    # Gemini API client
│   ├── agents/                 # Agent implementations
│   │   ├── executors.py        # Code generation & execution
│   │   └── prompts.py          # System prompts for each agent
│   ├── tools/                  # Tool definitions
│   │   └── definitions.py      # Gemini function calling schemas
│   └── utils/                  # Utilities
│       └── logging.py          # WebSocket manager & XML logging
├── web/                        # Web interface
│   ├── backend/
│   │   └── server.py           # FastAPI server
│   └── frontend/
│       ├── index.html          # Main UI
│       ├── app.js              # Chat & WebSocket logic
│       └── style.css           # Styling
├── data/
│   └── input/                  # Uploaded datasets (gitignored)
├── workspace/                  # Agent working directories (gitignored)
│   ├── preparation/            # Data prep outputs
│   ├── analysis/               # ML models
│   └── report/                 # Generated reports
├── outputs/                    # Final artifacts (gitignored)
├── shared_knowledge.xml        # Agent execution summaries
├── requirements.txt            # Python dependencies
├── .env                        # API keys (create this!)
└── README.md                   # This file
```

## API Endpoints

The backend exposes these REST endpoints:

### `GET /`
Serves the web UI (HTML interface)

### `POST /api/chat`
Main chat endpoint with file upload support

**Request** (multipart/form-data):
- `message` (required) - User message
- `session_id` (optional) - Session UUID
- `file` (optional) - CSV or Excel file upload (.csv or .xlsx)

**Response**:
```json
{
  "session_id": "uuid",
  "status": "processing" | "error"
}
```

### `WebSocket /ws`
Real-time log streaming endpoint

**Message Format**:
```json
{
  "type": "user|assistant|tool_call|tool_result",
  "header": "Display header",
  "message": "Content",
  "timestamp": "ISO timestamp"
}
```

### `GET /api/session/{session_id}`
Get session details (debugging)

### `GET /api/health`
Health check with connection stats

## Development

### Run CLI Mode (Legacy)

```bash
python -m src.main
```

Uses `INITIAL_QUERY` from `src/agents/prompts.py`

### Modify Agent Behavior

Edit system prompts in `src/agents/prompts.py`:
- `PREPARATION_AGENT_SYSTEM_PROMPT` - Data cleaning instructions
- `ANALYSIS_AGENT_SYSTEM_PROMPT` - ML model training instructions
- `REPORT_AGENT_PROMPT` - Report generation instructions

### Customize Orchestrator

Edit `src/core/orchestrator.py` to:
- Change agent selection logic
- Add new agent types
- Modify workflow sequence

### View Generated Code

Agent-generated Python scripts are saved to:
```
workspace/{agent_name}/generated_script.py
```

### Access Agent Outputs

- Cleaned data: `workspace/preparation/output_dataset.csv`
- Trained model: `workspace/analysis/model.joblib`
- Report: `workspace/report/analysis_report.txt`

## Troubleshooting

### Server won't start - Port in use
```bash
# Find and kill process on port 8080
lsof -ti :8080 | xargs kill -9
```

### WebSocket disconnected
- Check if server is running
- Refresh browser (Ctrl+Shift+R for hard refresh)
- Try incognito/private window

### File upload fails
- Ensure file is CSV (`.csv`) or Excel (`.xlsx`) format
- Check file size (FastAPI default limit: 16MB)
- Verify `python-multipart` and `openpyxl` are installed

### Agent execution fails
- Check `workspace/{agent}/generated_script.py` for errors
- Ensure all required libraries are installed
- Verify `.env` file has valid `GEMINI_API_KEY`

### Browser caching issues
Add version parameter to static assets in `index.html`:
```html
<script src="/static/app.js?v=6"></script>
```

## Key Technologies

- **Google Gemini 2.5 Flash** - LLM orchestration and code generation
- **FastAPI** - Modern async web framework
- **WebSockets** - Real-time bidirectional communication
- **Pandas & Scikit-learn** - Data processing and ML
- **Vanilla JavaScript** - No frontend framework dependencies

## Security Notes

- Sessions are stored in-memory (not persistent across server restarts)
- Uploaded files are saved to disk without encryption
- No authentication or authorization (single-user system)
- Generated code executes with server process permissions

## License

This project is for educational and research purposes.
