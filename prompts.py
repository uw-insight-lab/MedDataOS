SYSTEM_INSTRUCTION = """
You are an orchestrator for of an agent system.
Your goal is to propose an analysis plan for the given dataset.
You have 3 agents at your disposal. For each agent you should send structured query in a human readable format. Here's what agents do:
1 - Preparation agent: write python script for dataset cleaning
2 - Analysis agent: write python script to create ML model for the analysis
3 - Visualization agent: write create python script to create visualizaion

Preferably, follow the given sequence when calling agents.
Pass required infromation to each agent when making tool calls.
"""

INITIAL_QUERY = """
Here is a dataset you'll be working with:
<df.head()>
| patient\_id  | Age  | Sex    | ECOG PS | Smoking PY | Smoking Status | Ds Site    | Subsite         | T   | N   | M   | Stage | Path | HPV | Tx Modality | Chemo | RT Start | Dose | Fx  | Last FU | Status | Length FU | Date of Death | Cause of Death | Local | Date Local | Regional | Date Regional | Distant | Date Distant | 2nd Ca           | Date 2nd Ca | RADCURE-challenge | ContrastEnhanced |
| ------------ | ---- | ------ | ------- | ---------- | -------------- | ---------- | --------------- | --- | --- | --- | ----- | ---- | --- | ----------- | ----- | -------- | ---- | --- | ------- | ------ | --------- | ------------- | -------------- | ----- | ---------- | -------- | ------------- | ------- | ------------ | ---------------- | ----------- | ----------------- | ---------------- |
| RADCURE-0005 | 62.6 | Female | ECOG 0  | 50         | Ex-smoker      | Oropharynx | post wall       | T4b | N2c | NaN | NaN   | NaN  | NaN | NaN         | NaN   | NaN      | NaN  | NaN | NaN     | NaN    | NaN       | NaN           | NaN            | NaN   | NaN        | NaN      | NaN           | NaN     | NaN          | NaN              | NaN         | 0                 | 0                |
| RADCURE-0006 | 87.3 | Male   | ECOG 2  | 25         | Ex-smoker      | Larynx     | Glottis         | T1b | N0  | NaN | NaN   | NaN  | NaN | NaN         | NaN   | NaN      | NaN  | NaN | NaN     | NaN    | NaN       | NaN           | NaN            | NaN   | NaN        | NaN      | NaN           | NaN     | NaN          | NaN              | NaN         | 0                 | 1                |
| RADCURE-0007 | 49.9 | Male   | ECOG 1  | 15         | Ex-smoker      | Oropharynx | Tonsil          | T3  | N2b | NaN | NaN   | NaN  | NaN | NaN         | NaN   | NaN      | NaN  | NaN | NaN     | NaN    | NaN       | NaN           | NaN            | NaN   | NaN        | NaN      | NaN           | NaN     | NaN          | NaN              | NaN         | 0                 | 1                |
| RADCURE-0009 | 72.3 | Male   | ECOG 1  | 30         | Ex-smoker      | Unknown    | NaN             | T0  | N2c | NaN | NaN   | NaN  | NaN | NaN         | NaN   | NaN      | NaN  | NaN | NaN     | NaN    | NaN       | NaN           | NaN            | NaN   | NaN        | NaN      | NaN           | NaN     | NaN          | S   (suspicious) | 5/27/08     | 0                 | 0                |
| RADCURE-0010 | 59.7 | Female | ECOG 0  | 0          | Non-smoker     | Oropharynx | Tonsillar Fossa | T4b | N0  | NaN | NaN   | NaN  | NaN | NaN         | NaN   | NaN      | NaN  | NaN | NaN     | NaN    | NaN       | NaN           | NaN            | NaN   | NaN        | NaN      | NaN           | NaN     | NaN          | NaN              | NaN         | 0                 | 0                |
</df.head()>
Call the agents to accomplish the task.
""" 

PREPARATION_AGENT = """

"""

ANALYSIS_AGENT = """

"""

VISUALIZATION_AGENT = """

"""