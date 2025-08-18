# Custom inputs
from logging_utils import log_assistant, write_agent_summary, read_agent_summary
from prompts import PREPARATION_AGENT_SYSTEM_PROMPT, ANALYSIS_AGENT_SYSTEM_PROMPT, REPORT_AGENT_PROMPT, SUMMARIZER_PROMPT
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
        
        prompt = SUMMARIZER_PROMPT.format(
            script_content=script_content,
            execution_output=execution_output
        )
        
        client = create_client()
        contents = [types.Content(
            role="user", parts=[types.Part(text=prompt)]
        )]
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents
        )
        summary = response.candidates[-1].content.parts[-1].text
        log_assistant(f"Steps summary: {summary}")
        
        # Save summary to XML file
        write_agent_summary(agent_type, summary)
        return summary
        
    except Exception as e:
        log_assistant(f"Could not generate summary: {str(e)}")
        return None

def execute_agent(plan, agent_config):
    """
    Unified agent executor function.
    
    Args:
        plan (str): The plan/instructions for the agent
        agent_config (dict): Configuration containing:
            - 'system_prompt': The system prompt for the agent
            - 'agent_name': Name of the agent (for folder/file paths)
            
    Returns:
        str: Execution summary or error message
    """
    client = create_client()
    config = types.GenerateContentConfig(
        system_instruction=agent_config['system_prompt']
    )
    # Create contents with the plan
    contents = [types.Content(
        role="user", parts=[types.Part(text=plan)]
    )]
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
    script_path = os.path.join(agent_config['agent_name'], 'script.py')
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    
    with open(script_path, 'w') as f:
        f.write(python_code)
    
    # Execute the generated script
    execution_result = execute_python_file(script_path)
    log_assistant(f"Script execution result: {execution_result}")
    
    # If successful, return summary; otherwise return error
    if execution_result.startswith("Successfully executed"):
        summary = summarize_steps(script_path, execution_result, agent_config['agent_name'])
        return summary if summary else execution_result
    else:
        return execution_result

# Wrapper functions for backwards compatibility
def execute_preparation_agent(preparation_plan):
    return execute_agent(preparation_plan, {
        'system_prompt': PREPARATION_AGENT_SYSTEM_PROMPT,
        'agent_name': 'preparation_agent'
    })

def execute_analysis_agent(analysis_plan):
    return execute_agent(analysis_plan, {
        'system_prompt': ANALYSIS_AGENT_SYSTEM_PROMPT,
        'agent_name': 'analysis_agent'
    })

def execute_report_agent(report_plan):
    return execute_agent(report_plan, {
        'system_prompt': REPORT_AGENT_PROMPT,
        'agent_name': 'report_agent'
    }) 