# Custom inputs
from logging_utils import log_assistant

# Other imports
from google import genai
from google.genai import types
import pandas as pd
import numpy as np
from tempfile import NamedTemporaryFile
import os
import subprocess
import sys
from dotenv import load_dotenv
load_dotenv()

# Get API key from environment variable
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in your .env file.")

def execute_python_file(file_path):
    try:
        if not os.path.exists(file_path):
            return f"Error: File {file_path} does not exist"
            
        if not file_path.endswith('.py'):
            return f"Error: File {file_path} is not a Python file"
            
        # Execute the Python file using the same Python interpreter
        result = subprocess.run([sys.executable, file_path], 
                              capture_output=True,
                              text=True,
                              check=True)
        
        if result.returncode == 0:
            return f"Successfully executed {file_path}\nOutput:\n{result.stdout}"
        else:
            return f"Error executing {file_path}\nError:\n{result.stderr}"
            
    except subprocess.CalledProcessError as e:
        return f"Error executing {file_path}\nError:\n{e.stderr}"
    except Exception as e:
        return f"Unexpected error executing {file_path}\nError: {str(e)}"

def execute_preparation_agent(preparation_plan):    
    PREPARATION_AGENT_SYSTEM_PROMPT = """
You are a data preparation agent.
Clean, validate, and standardize the input data for analysis, as you are instructed.
Do not perform any analysis or interpretation.
Input dataset in the project directory: /Users/mbidnyj/Dev/multi-agent-system/preparation_agent/input_dataset.csv
Data dictionary: /Users/mbidnyj/Dev/multi-agent-system/preparation_agent/data_dictionary.csv
Output dataset in the root directory: /Users/mbidnyj/Dev/multi-agent-system/preparation_agent/output_dataset.csv
You have pandas and numpy libraries at your disposal.
Output nothing but only python script.
Start from:
import...
"""
    
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )
    config = types.GenerateContentConfig(
        system_instruction=PREPARATION_AGENT_SYSTEM_PROMPT
    )
    contents = [
        types.Content(
            role="user", parts=[types.Part(text=preparation_plan)]
        )
    ]
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=config
    )
    python_code = response.candidates[-1].content.parts[-1].text
    
    # Clean up code block markers if they exist
    python_code = python_code.strip()
    if python_code.startswith("```python"):
        python_code = python_code[len("```python"):].strip()
    elif python_code.startswith("```"):
        python_code = python_code[len("```"):].strip()
    if python_code.endswith("```"):
        python_code = python_code[:-len("```")].strip()

    # Store python code into script.py file
    script_path = os.path.join('preparation_agent', 'script.py')
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    
    with open(script_path, 'w') as f:
        f.write(python_code)
    
    # Execute the generated script
    execution_result = execute_python_file(script_path)
    log_assistant(f"Script execution result: {execution_result}")

    return execution_result

def execute_analysis_agent(analysis_plan):
    ANALYSIS_AGENT_SYSTEM_PROMPT = """
You are an analysis agent.
Execute the provided analysis plan on the prepared data, as you are instructed.
Do not modify the plan or add extra insights.
Output nothing but the python script.
You have scikit-learn library at your disposal for the model training and joblib to store the model.
Store the model at /Users/mbidnyj/Dev/multi-agent-system/analysis_agent/model.joblib file.
Output nothing but only python script.
Start from:
import...
"""
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )
    config = types.GenerateContentConfig(
        system_instruction=ANALYSIS_AGENT_SYSTEM_PROMPT
    )
    contents = [
        types.Content(
            role="user", parts=[types.Part(text=analysis_plan)]
        )
    ]
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=config
    )
    python_code = response.candidates[-1].content.parts[-1].text
    
    # Clean up code block markers if they exist
    python_code = python_code.strip()
    if python_code.startswith("```python"):
        python_code = python_code[len("```python"):].strip()
    elif python_code.startswith("```"):
        python_code = python_code[len("```"):].strip()
    if python_code.endswith("```"):
        python_code = python_code[:-len("```")].strip()

    # Store python code into script.py file
    script_path = os.path.join('analysis_agent', 'script.py')
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    
    with open(script_path, 'w') as f:
        f.write(python_code)
    
    # Execute the generated script
    execution_result = execute_python_file(script_path)
    log_assistant(f"Script execution result: {execution_result}")

    return execution_result

def execute_visualization_agent(visualization_plan):    
    VISUALIZATION_AGENT_PROMPT = """
You are a visualization agent.
Having results of the model execution, get the most useful data insight and write python script to visualize it.
You have mathplotlib and seabord libraries at your disposal.
Store the image at /Users/mbidnyj/Dev/multi-agent-system/visualization_agent/insight.png file.
Output nothing but only python script.
Start from:
import...
"""
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )
    config = types.GenerateContentConfig(
        system_instruction=VISUALIZATION_AGENT_PROMPT
    )
    contents = [
        types.Content(
            role="user", parts=[types.Part(text=visualization_plan)]
        )
    ]
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=config
    )
    python_code = response.candidates[-1].content.parts[-1].text
    
    # Clean up code block markers if they exist
    python_code = python_code.strip()
    if python_code.startswith("```python"):
        python_code = python_code[len("```python"):].strip()
    elif python_code.startswith("```"):
        python_code = python_code[len("```"):].strip()
    if python_code.endswith("```"):
        python_code = python_code[:-len("```")].strip()

    # Store python code into script.py file
    script_path = os.path.join('visualization_agent', 'script.py')
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    
    with open(script_path, 'w') as f:
        f.write(python_code)
    
    # Execute the generated script
    execution_result = execute_python_file(script_path)
    log_assistant(f"Script execution result: {execution_result}")

    return execution_result 