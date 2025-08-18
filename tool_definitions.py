from google.genai import types

prepare_data_for_analysis = {
    "name": "prepare_data_for_analysis",
    "description": "Write python scipt to execute preparation plan of what should be done with dataset",
    "parameters": {
        "type": "object",
        "properties": {
            "preparation_plan": {
                "type": "string",
                "description": "Provide comprehensive preparation plan for the given dataset to make it ready for the futher data analysis. Format the plan as a simple numbered list without any markdown formatting, like: 1. First step description 2. Second step description 3. Third step description 4..."
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

visualize_analysis_results = {
    "name": "visualize_analysis_results",
    "description": "Provide visualizations of the analysis main features to present data conveniently",
    "parameters": {
        "type": "object",
        "properties": {
            "visualization_plan": {
                "type": "string",
                "description": "Write python script to build visualization using mathplotlib or seaborn libraries. Format the plan as a simple numbered list without any markdown formatting, like: 1. First step description 2. Second step description 3. Third step description 4..."
            }
        },
        "required": ["visualization_plan"]
    }
}

# Create a tools configuration for Gemini
tools = types.Tool(function_declarations=[prepare_data_for_analysis, prepare_analysis, visualize_analysis_results]) 