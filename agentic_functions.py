preparation_agent = {
    "name": "data_preparation_agent",
    "description": "Write python scipt to execute preparation plan of what should be done with dataset",
    "parameters": {
        "type": "object",
        "properties": {
            "preparation_plan": {
                "type": "string",
                "description": "Provide comprehensive preparation plan for the given dataset to make it ready for the futher data analysis"
            }
        },
        "required": "preparation_plan"
    }
}

analysis_agent = {
    "name": "data_analysis_agent",
    "description": "Write python script to execute analysis plan with input dataset",
    "parameters": {
        "type": "object",
        "properties": {
            "analysis_task": {
                "type": "string",
                "description": "Write python script to execute analysis plan with all given input data"
            }
        },
        "required": "preparation_task"
    }
}

visualization_agent = {
    "name": "data_visualization_agent",
    "description": "Provide visualizations to present data conveniently",
    "parameters": {
        "type": "object",
        "properties": {
            "analysis_task": {
                "type": "string",
                "description": "Write python script to build visualization using mathplotlib or seaborn libraries"
            }
        },
        "required": "preparation_task"
    }
}

orchestrator_prompt = """You are an orchestrator for of an agent system. Your goal is to propose an analysis plan for the given dataset:
df.head()
Once it’s done, you may be asked about possible corrections, after manual approval. You have 3 agents at your disposal. For each agent you should send structured query in a human readable format. Here are agents:
1 - Preparation agent: clean loaded data
2 - Analysis agent: create a model and run it
3 - Visualization agent: presents results to the user

All of them are available as via function calling. Call each
"""