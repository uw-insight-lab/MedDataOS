"""
Tool definitions for Gemini function calling.
Defines the interface for all specialized agents in the system.
"""
from google.genai import types

prepare_data_for_analysis = {
    "name": "prepare_data_for_analysis",
    "description": "Write python script to execute preparation plan of what should be done with dataset",
    "parameters": {
        "type": "object",
        "properties": {
            "preparation_plan": {
                "type": "string",
                "description": "Provide comprehensive preparation plan for the given dataset to make it ready for the further data analysis. Format the plan as a simple numbered list without any markdown formatting, like: 1. First step description 2. Second step description 3. Third step description 4..."
            }
        },
        "required": ["preparation_plan"]
    }
}

prepare_analysis = {
    "name": "prepare_analysis",
    "description": "Write python script to execute analysis plan with input dataset",
    "parameters": {
        "type": "object",
        "properties": {
            "analysis_plan": {
                "type": "string",
                "description": "Write python script to execute analysis plan with all given input data. Format the plan as a simple numbered list without any markdown formatting, like: 1. First step description 2. Second step description 3. Third step description 4..."
            }
        },
        "required": ["analysis_plan"]
    }
}

classify_chest_xray = {
    "name": "classify_chest_xray",
    "description": "Analyzes chest X-ray images from URL to detect and classify 18 different pathological conditions using a pre-trained deep learning model. Returns probability scores for each pathology, high-confidence findings, summary statistics, and clinical interpretation-ready results.",
    "parameters": {
        "type": "object",
        "properties": {
            "image_url": {
                "type": "string",
                "description": "URL to the chest X-ray image (JPEG format) to be analyzed."
            }
        },
        "required": ["image_url"]
    }
}

# Create a tools configuration for Gemini
tools = types.Tool(function_declarations=[
    prepare_data_for_analysis,
    prepare_analysis,
    classify_chest_xray
])
