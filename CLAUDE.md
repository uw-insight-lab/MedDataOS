# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-agent data analysis system that uses Google's Gemini API to orchestrate three specialized agents for automated machine learning workflows. The system processes healthcare datasets through a sequential pipeline of data preparation, analysis, and visualization.

### Core Architecture

The system follows a tool-calling orchestration pattern with these key components:

- **Orchestrator Agent** (`agentic_pipeline.py`): Main controller that calls specialized agents in sequence
- **Agent Executors** (`agent_executors.py`): Functions that execute each specialized agent by generating and running Python scripts
- **Tool Definitions** (`tool_definitions.py`): Gemini function calling definitions for the three agents
- **Shared Knowledge System** (`shared_knowledge.xml`): XML-based persistence for agent execution summaries

### Agent Workflow

1. **Preparation Agent**: Cleans and preprocesses raw CSV data using pandas/numpy
2. **Analysis Agent**: Creates ML models using scikit-learn and saves them with joblib
3. **Report Agent**: Generates comprehensive text reports with model insights and recommendations

Each agent:
- Receives a structured plan as input
- Generates Python code based on system prompts
- Executes the code and saves outputs to designated directories
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
python agentic_pipeline.py
```

## Data Flow

Input: `preparation_agent/input_dataset.csv` (raw healthcare data)
→ Preparation: `preparation_agent/output_dataset.csv` (cleaned data)
→ Analysis: `analysis_agent/model.joblib` (trained ML model)
→ Report: `report_agent/analysis_report.txt` (comprehensive analysis report)

## Agent Directories

Each agent operates in its own directory with specific input/output files:
- `preparation_agent/`: Input CSV → output CSV + generated script
- `analysis_agent/`: Cleaned data → trained model + metrics + generated script  
- `report_agent/`: Model results → text analysis report + generated script

## Shared Knowledge System

Agent execution summaries are stored in `shared_knowledge.xml` using the logging utilities in `logging_utils.py`. Each agent can read previous agent summaries to understand the workflow context.