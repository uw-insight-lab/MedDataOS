"""
Agent executor functions for running specialized agents.
"""
import os
import subprocess
import sys
import requests
import json

from google.genai import types

from src.utils.logging import log_assistant, write_agent_summary, read_agent_summary
from src.agents.prompts import (
    PREPARATION_AGENT_SYSTEM_PROMPT,
    ANALYSIS_AGENT_SYSTEM_PROMPT,
    REPORT_AGENT_PROMPT,
    SUMMARIZER_PROMPT
)
from src.core.gemini_client import create_client, create_response


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


def summarize_steps(script_path, execution_output, agent_type):
    """
    Generate a summary of executed steps and save to XML.

    Args:
        script_path (str): Path to the executed script
        execution_output (str): Output from script execution
        agent_type (str): Type of agent (preparation, analysis, report)

    Returns:
        str: Generated summary or None if error
    """
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

    # Store python code into generated_script.py file in workspace
    script_path = os.path.join('workspace', agent_config['agent_name'], 'generated_script.py')
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


def execute_report_agent(report_plan):
    """Execute the report generation agent."""
    return execute_agent(report_plan, {
        'system_prompt': REPORT_AGENT_PROMPT,
        'agent_name': 'report'
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

        # Send POST request to localhost:8000/classify/url
        response = requests.post(
            "http://localhost:8000/classify/url",
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
        error_msg = "Could not connect to chest X-ray classification service at localhost:8000"
        log_assistant(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Unexpected error during chest X-ray classification: {str(e)}"
        log_assistant(error_msg)
        return error_msg
