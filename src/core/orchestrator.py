"""
Main orchestrator for the multi-agent system.
Coordinates between specialized agents using Gemini's function calling.
"""
from google.genai import types

from src.tools.definitions import tools
from src.utils.logging import log_user, log_assistant, log_tool_call, log_tool_result
from src.agents.prompts import SYSTEM_INSTRUCTION, INITIAL_QUERY
from src.agents.executors import execute_agent, execute_chest_xray_agent
from src.agents.prompts import (
    PREPARATION_AGENT_SYSTEM_PROMPT,
    ANALYSIS_AGENT_SYSTEM_PROMPT
)
from src.core.gemini_client import create_client, create_config, create_contents


def run_pipeline(user_query: str = None, conversation_history: list = None, uploaded_file: str = None,
                  patient_id: str = None, patient_info: dict = None):
    """
    Execute the main orchestration pipeline.

    Args:
        user_query (str): User's query/task to execute. If None, uses INITIAL_QUERY from prompts.
        conversation_history (list): Optional conversation history in format:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        uploaded_file (str): Optional path to uploaded .xlsx file for analysis
        patient_id (str): Optional patient identifier (e.g. "P0001")
        patient_info (dict): Optional patient info dict with age, sex, blood_type, allergies, conditions

    This function:
    1. Initializes the Gemini client and configuration
    2. Processes the user query with conversation context
    3. Loops through tool calls, executing specialized agents
    4. Logs all interactions
    """
    client = create_client()

    # Modify system instruction if file is uploaded
    system_instruction = SYSTEM_INSTRUCTION

    # Prepend patient context when available
    if patient_id and patient_info:
        patient_name = patient_info.get('name', patient_id)
        patient_block = (
            f"\n\nACTIVE PATIENT: {patient_name} ({patient_id})\n"
            f"Age: {patient_info.get('age')}  Sex: {patient_info.get('sex')}  "
            f"Blood Type: {patient_info.get('blood_type', 'N/A')}\n"
            f"Allergies: {', '.join(patient_info.get('allergies', [])) or 'None'}\n"
            f"Conditions: {', '.join(patient_info.get('conditions', [])) or 'None'}\n"
            f"All queries in this conversation relate to this patient.\n"
        )
        system_instruction = patient_block + system_instruction
    if uploaded_file:
        system_instruction = f"""{SYSTEM_INSTRUCTION}

IMPORTANT: The user has uploaded a file at: {uploaded_file}
This file should be used as input for the data preparation agent.
You MUST call the prepare_data_for_analysis tool first to process this uploaded file.
After preparation, proceed with prepare_analysis tool if ML training is requested.
"""

    config = create_config(tools, system_instruction)

    # Convert conversation history to Gemini format
    contents = []
    if conversation_history:
        for msg in conversation_history[:-1]:  # All except last (current) message
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=msg["content"])]
            ))

    # Use provided query or default to INITIAL_QUERY
    query = user_query if user_query else INITIAL_QUERY

    # Enhance query with file information if provided
    if uploaded_file:
        query = f"""{query}

UPLOADED FILE: {uploaded_file}
Please analyze this uploaded dataset by:
1. Preparing and cleaning the data
2. Performing analysis as requested
"""

    # Add current query to contents
    contents.append(types.Content(
        role="user", parts=[types.Part(text=query)]
    ))
    log_user(query)

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=config
    )

    contents.append(response.candidates[-1].content)
    tool_call = response.candidates[-1].content.parts[-1].function_call

    # Tool calling loop
    while tool_call and tool_call.name:
        # Agent configuration mapping
        agent_configs = {
            "prepare_data_for_analysis": {
                'system_prompt': PREPARATION_AGENT_SYSTEM_PROMPT,
                'agent_name': 'preparation',
                'plan_key': 'preparation_plan'
            },
            "prepare_analysis": {
                'system_prompt': ANALYSIS_AGENT_SYSTEM_PROMPT,
                'agent_name': 'analysis',
                'plan_key': 'analysis_plan'
            },
            "classify_chest_xray": {
                'function': execute_chest_xray_agent,
                'param_key': 'image_url'
            }
        }

        # Detect if it was a tool call
        if tool_call:
            # Lookup agent configuration
            agent_config = agent_configs.get(tool_call.name)
            if agent_config:
                # Check if this is the special chest X-ray tool
                if tool_call.name == "classify_chest_xray":
                    # Special handling for chest X-ray classification
                    image_url = tool_call.args.get(agent_config['param_key'])
                    log_tool_call(tool_call.name, image_url)

                    result = agent_config['function'](image_url)
                    log_tool_result(result)
                else:
                    # Regular agent execution
                    plan = tool_call.args.get(agent_config['plan_key'])
                    log_tool_call(tool_call.name, plan)

                    result = execute_agent(plan, agent_config)
                    log_tool_result(result)
            else:
                raise ValueError(f"Unknown tool: {tool_call.name}")

        # Fallback: model responded with text
        elif response:
            result = response.candidates[-1].content.parts[-1].text
            log_assistant(result)

        # Attach response to history
        function_response_part = types.Part.from_function_response(
            name=tool_call.name,
            response={"result": result},
        )
        contents.append(types.Content(role="user", parts=[function_response_part]))

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=contents,
            config=config
        )

        if (
            response.candidates and
            response.candidates[-1].content and
            response.candidates[-1].content.parts and
            response.candidates[-1].content.parts[-1].function_call
        ):
            tool_call = response.candidates[-1].content.parts[-1].function_call
        else:
            tool_call = None

    # Get final assistant response
    final_response = response.candidates[-1].content.parts[-1].text
    log_assistant(final_response)

    return final_response
