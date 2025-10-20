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
    ANALYSIS_AGENT_SYSTEM_PROMPT,
    REPORT_AGENT_PROMPT
)
from src.core.gemini_client import create_client, create_config, create_contents


def run_pipeline():
    """
    Execute the main orchestration pipeline.

    This function:
    1. Initializes the Gemini client and configuration
    2. Processes the initial query
    3. Loops through tool calls, executing specialized agents
    4. Logs all interactions
    """
    client = create_client()
    config = create_config(tools, SYSTEM_INSTRUCTION)

    # Initialize conversation history
    history = []
    contents = create_contents(history)

    # Add initial query to contents
    contents.append(types.Content(
        role="user", parts=[types.Part(text=INITIAL_QUERY)]
    ))
    log_user(INITIAL_QUERY)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
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
            "generate_analysis_report": {
                'system_prompt': REPORT_AGENT_PROMPT,
                'agent_name': 'report',
                'plan_key': 'report_plan'
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
            model="gemini-2.5-flash",
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

    log_assistant(response.candidates[-1].content.parts[-1].text)
