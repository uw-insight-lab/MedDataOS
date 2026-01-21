"""
Agent executor functions for running specialized agents.
"""
import os
import subprocess
import sys
import requests
import json

from google.genai import types

from src.utils.logging import log_assistant
from src.agents.prompts import (
    PREPARATION_AGENT_SYSTEM_PROMPT,
    ANALYSIS_AGENT_SYSTEM_PROMPT
)
from src.core.gemini_client import create_client, create_response

# External service URLs (configurable via environment)
CHEST_XRAY_SERVICE_URL = os.getenv("CHEST_XRAY_SERVICE_URL", "http://localhost:8000/classify/url")


def execute_python_file(file_path):
    """
    Execute a Python file and capture its output.

    Args:
        file_path (str): Path to the Python file to execute

    Returns:
        str: Success message with output or error message
    """
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
    response = create_response(client, "gemini-2.5-pro", contents, config)
    python_code = response.candidates[-1].content.parts[-1].text

    # Clean up code block markers if they exist
    python_code = python_code.strip()
    if python_code.startswith("```python"):
        python_code = python_code[len("```python"):].strip()
    elif python_code.startswith("```"):
        python_code = python_code[len("```"):].strip()
    if python_code.endswith("```"):
        python_code = python_code[:-len("```")].strip()

    # Store python code into generated_script.py file in workspace
    script_path = os.path.join('workspace', agent_config['agent_name'], 'generated_script.py')
    os.makedirs(os.path.dirname(script_path), exist_ok=True)

    with open(script_path, 'w') as f:
        f.write(python_code)

    # Execute the generated script
    execution_result = execute_python_file(script_path)
    log_assistant(f"Script execution result: {execution_result}")

    # Return execution result directly (summarization removed for clarity)
    if execution_result.startswith("Successfully executed"):
        return f"{agent_config['agent_name'].title()} agent completed successfully"
    else:
        return execution_result


# Wrapper functions for backwards compatibility
def execute_preparation_agent(preparation_plan):
    """Execute the data preparation agent."""
    return execute_agent(preparation_plan, {
        'system_prompt': PREPARATION_AGENT_SYSTEM_PROMPT,
        'agent_name': 'preparation'
    })


def execute_analysis_agent(analysis_plan):
    """Execute the data analysis agent."""
    return execute_agent(analysis_plan, {
        'system_prompt': ANALYSIS_AGENT_SYSTEM_PROMPT,
        'agent_name': 'analysis'
    })


def execute_chest_xray_agent(image_url):
    """
    Execute chest X-ray classification using external API.

    Args:
        image_url (str): URL of the chest X-ray image to classify

    Returns:
        str: JSON response with probability scores for each pathology
    """
    try:
        # Prepare the payload
        payload = {
            "image_url": image_url
        }

        # Send POST request to chest X-ray classification service
        response = requests.post(
            CHEST_XRAY_SERVICE_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )

        # Check if request was successful
        if response.status_code == 200:
            # Return the JSON response as is
            result_json = response.json()
            log_assistant(f"Chest X-ray classification completed for {image_url}")
            return json.dumps(result_json, indent=2)
        else:
            error_msg = f"API request failed with status {response.status_code}: {response.text}"
            log_assistant(error_msg)
            return error_msg

    except requests.exceptions.Timeout:
        error_msg = "Request timed out - chest X-ray classification service may be slow"
        log_assistant(error_msg)
        return error_msg
    except requests.exceptions.ConnectionError:
        error_msg = f"Could not connect to chest X-ray classification service at {CHEST_XRAY_SERVICE_URL}"
        log_assistant(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error during chest X-ray classification: {str(e)}"
        log_assistant(error_msg)
        return error_msg
