# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-agent data analysis system that uses Google's Gemini API to orchestrate specialized agents for automated machine learning workflows. The system processes healthcare datasets through a sequential pipeline of data preparation, analysis, and reporting.

### Core Architecture

The system follows a tool-calling orchestration pattern with these key components:

**Source Code (`src/`):**
- `src/main.py` - Entry point for the application
- `src/core/orchestrator.py` - Main controller that calls specialized agents in sequence
- `src/core/gemini_client.py` - Gemini API client setup and configuration
- `src/agents/executors.py` - Functions that execute specialized agents by generating and running Python scripts
- `src/agents/prompts.py` - System prompts for orchestrator and specialized agents
- `src/tools/definitions.py` - Gemini function calling definitions for all agents
- `src/utils/logging.py` - Console logging and XML-based shared knowledge management

**Data & Workspace:**
- `data/input/` - Input datasets (CSV files)
- `workspace/` - Agent working directories (gitignored)
  - `workspace/preparation/` - Data preparation outputs
  - `workspace/analysis/` - ML model outputs
  - `workspace/report/` - Generated reports
- `outputs/` - Final artifacts (gitignored)
- `shared_knowledge.xml` - XML-based persistence for agent execution summaries

### Agent Workflow

1. **Preparation Agent**: Cleans and preprocesses raw CSV data using pandas/numpy
2. **Analysis Agent**: Creates ML models using scikit-learn and saves them with joblib
3. **Report Agent**: Generates comprehensive text reports with model insights and recommendations
4. **Chest X-ray Agent**: Classifies chest X-ray images using external API

Each agent:
- Receives a structured plan as input
- Generates Python code based on system prompts
- Executes the code and saves outputs to workspace directories
- Returns execution summaries stored in `shared_knowledge.xml`

## Key Dependencies

Required packages (from `requirements.txt`):
- `pandas>=2.0.0`, `numpy>=1.24.0` - Data manipulation
- `scikit-learn>=1.3.0`, `joblib>=1.3.0` - ML and model persistence  
- `matplotlib>=3.7.0`, `seaborn>=0.12.0` - Visualization
- `python-dotenv>=1.0.0` - Environment management

## Running the System

```bash
# Set up environment
pip install -r requirements.txt

# Configure API key in .env file
echo "GEMINI_API_KEY=your_api_key_here" > .env

# Run the main pipeline
python -m src.main
```

## Data Flow

Input: `data/input/dataset.csv` (raw healthcare data)
→ Preparation: `workspace/preparation/output_dataset.csv` (cleaned data)
→ Analysis: `workspace/analysis/model.joblib` (trained ML model)
→ Report: `workspace/report/analysis_report.txt` (comprehensive analysis report)

## Directory Structure

```
src/                    # Source code
├── main.py            # Entry point
├── core/              # Core orchestration
│   ├── orchestrator.py
│   └── gemini_client.py
├── agents/            # Agent execution
│   ├── executors.py
│   └── prompts.py
├── tools/             # Tool definitions
│   └── definitions.py
└── utils/             # Utilities
    └── logging.py

data/input/            # Input datasets
workspace/             # Agent workspaces (gitignored)
├── preparation/       # Generated scripts & cleaned data
├── analysis/          # Generated scripts & ML models
└── report/            # Generated scripts & reports
outputs/               # Final artifacts (gitignored)
```

## Shared Knowledge System

Agent execution summaries are stored in `shared_knowledge.xml` using the logging utilities in `src/utils/logging.py`. Each agent can read previous agent summaries to understand the workflow context.

## Development Notes

- All source code is in the `src/` directory with proper module structure
- Old files (`agentic_pipeline.py`, `agent_executors.py`, etc.) are deprecated - use the new `src/` structure
- Generated scripts are saved as `generated_script.py` in respective workspace directories
- The system uses Python's module import system - run with `python -m src.main`