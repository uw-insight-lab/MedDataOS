# Each execution result is saved into shared logs

# Custom Imports
from tool_definitions import tools
from logging_utils import log_user, log_assistant, log_tool_call, log_tool_result
from prompts import SYSTEM_INSTRUCTION, INITIAL_QUERY
from agent_executors import (
    execute_preparation_agent,
    execute_analysis_agent,
    execute_visualization_agent
)

import os
from dotenv import load_dotenv
load_dotenv()

# Get API key from environment variable
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in your .env file.")

from google import genai
from google.genai import types

# ---------------------

client = genai.Client(
    api_key=GEMINI_API_KEY
)
config = types.GenerateContentConfig(
    tools=[tools],
    system_instruction=SYSTEM_INSTRUCTION
)

contents = [
    types.Content(
        role="user", parts=[types.Part(text=INITIAL_QUERY)]
    )
]
log_user(INITIAL_QUERY)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=contents,
    config=config
)

contents.append(response.candidates[-1].content)
tool_call = response.candidates[-1].content.parts[-1].function_call

# Tool calling in the loop
while tool_call and tool_call.name:
    # Tool-function mapping 
    tool_functions = {
        "prepare_data_for_analysis": execute_preparation_agent,
        "prepare_analysis": execute_analysis_agent,
        "visualize_analysis_results": execute_visualization_agent
    }
    # Detect if it was a tool call
    if tool_call:
        # Lookup and call corresponding tool function
        tool_func = tool_functions.get(tool_call.name)
        if tool_func:
            # Extract the relevant plan based on tool name
            plan_types = {
                "prepare_data_for_analysis": "preparation_plan",
                "prepare_analysis": "analysis_plan",
                "visualize_analysis_results": "visualization_plan"
            }
            plan_key = plan_types.get(tool_call.name)
            if plan_key:
                plan = tool_call.args.get(plan_key)
                log_tool_call(tool_call.name, plan)
            
            result = tool_func(plan)
            log_tool_result(result)
        else:
            raise ValueError(f"Unknown tool: {tool_call.name}")

    # Fallback: model responded with text
    elif response:
        result = response.candidates[-1].content.parts[-1].text
        log_assistant(result)

    # Attach respose to history
    function_response_part = types.Part.from_function_response(
        name=tool_call.name,
        response={"result": result},
    )
    contents.append(types.Content(role="user", parts=[function_response_part]))

    # call LLM once again
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