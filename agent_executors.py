# Custom inputs
from logging_utils import log_assistant, write_agent_summary, read_agent_summary
from prompts import PREPARATION_AGENT_SYSTEM_PROMPT, ANALYSIS_AGENT_SYSTEM_PROMPT, VISUALIZATION_AGENT_PROMPT
from genai_setup import create_client, create_config, create_contents, create_response

# Other imports
from google import genai
from google.genai import types
import pandas as pd
import numpy as np
from tempfile import NamedTemporaryFile
import os
import subprocess
import sys

def execute_python_file(file_path):
    try:
        if not os.path.exists(file_path):
            return f"Error: File {file_path} does not exist"
            
        if not file_path.endswith('.py'):
            return f"Error: File {file_path} is not a Python file"
            
        # Execute the Python file using the same Python interpreter
        result = subprocess.run([sys.executable, file_path], 
                              capture_output=True,
                              text=True)
        
        if result.returncode == 0:
            return f"Successfully executed {file_path}\nOutput:\n{result.stdout}"
        else:
            return f"Error executing {file_path}\nError:\n{result.stderr}"
            
    except subprocess.CalledProcessError as e:
        return f"Error executing {file_path}\nError:\n{e.stderr}"
    except Exception as e:
        return f"Unexpected error executing {file_path}\nError: {str(e)}"

def summarize_steps(script_path, execution_output, agent_type):
    """Simple function to summarize what steps were actually performed and save to XML"""
    try:
        # Read the executed script
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        prompt = f"""Based on this executed Python script and its output, summarize the actual steps that were performed.

Script:
{script_content}

Execution Output:
{execution_output}

IMPORTANT: Format your response as a simple numbered list without any markdown, bold text, or special formatting. Use this exact format:
1. First step description with details
2. Second step description with details 
3. Third step description with details
...

Do not use **bold**, *italics*, or any markdown formatting. Just provide a clean numbered list of what was actually accomplished."""
        
        client = create_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        response = create_response(client, "gemini-2.5-flash", contents, config)
        summary = response.candidates[-1].content.parts[-1].text
        log_assistant(f"Steps summary: {summary}")
        
        # Save summary to XML file
        write_agent_summary(agent_type, summary)
        return summary
        
    except Exception as e:
        log_assistant(f"Could not generate summary: {str(e)}")
        return None

def execute_preparation_agent(preparation_plan):    
    client = create_client()
    config = create_config([], PREPARATION_AGENT_SYSTEM_PROMPT)
    # Create history
    # Pass in correct format
    contents = create_contents(history)
    response = create_response(client, "gemini-2.5-flash", contents, config)
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
    
    # If successful, return summary; otherwise return error
    if execution_result.startswith("Successfully executed"):
        summary = summarize_steps(script_path, execution_result, "preparation_agent")
        return summary if summary else execution_result
    else:
        return execution_result

def execute_analysis_agent(analysis_plan):
    client = create_client()
    config = create_config([], ANALYSIS_AGENT_SYSTEM_PROMPT)
    # Define history
    # Pass in the correct format
    contents = create_contents(history)
    response = create_response(client, "gemini-2.5-flash", contents, config)
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
    
    # If successful, return summary; otherwise return error
    if execution_result.startswith("Successfully executed"):
        summary = summarize_steps(script_path, execution_result, "analysis_agent")
        return summary if summary else execution_result
    else:
        return execution_result

def execute_visualization_agent(visualization_plan):    
    client = create_client()
    config = create_config([], VISUALIZATION_AGENT_PROMPT)
    # Define history
    # Pass in the correct format
    contents = create_contents(history)
    response = create_response(client, "gemini-2.5-flash", contents, config)
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
    
    # If successful, return summary; otherwise return error
    if execution_result.startswith("Successfully executed"):
        summary = summarize_steps(script_path, execution_result, "visualization_agent")
        return summary if summary else execution_result
    else:
        return execution_result 