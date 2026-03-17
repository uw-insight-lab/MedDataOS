# Multimodal Medical Agent Framework — Design Spec

## Overview

Replace the existing 3-tool backend (data preparation, ML analysis, chest X-ray classification) with a 7-agent multimodal medical analysis framework. Each agent corresponds to a patient data modality. Agents use hardcoded stub responses per patient, with a clean interface for swapping in real models later.

The frontend is already built and expects this exact format — no frontend changes needed.

## Architecture

### Pipeline (3 stages)

1. **Orchestrator** — Gemini 3.1 Pro with function calling. Receives user query + patient context, decides which modality tools to call, collects results, then composes a narrative response with `[cite:N]` tokens.

2. **Knowledge Bus** — Separate Gemini 3.1 Pro call. Receives all findings from queried modalities, returns `supported_by` / `contradicted_by` cross-references per finding. Only fires when 2+ modalities are queried.

3. **JSON Assembly** — Deterministic Python code. Wraps Gemini's narrative text and the enriched findings into the `{"response": "...", "citations": [...]}` JSON the frontend expects.

### Data Flow

```
User Query + Patient Context
        │
        ▼
┌─────────────────────────────────┐
│  ORCHESTRATOR (Gemini 3.1 Pro)  │
│  Decides which tools to call    │
│  Can call multiple in parallel  │
└──────────┬──────────────────────┘
           │ function_call(s)
           ▼
┌─────────────────────────────────┐
│  AGENT REGISTRY                 │
│  analyze_ecg → EcgAgent         │
│  analyze_chest_xray → ...       │
│  Each returns Finding dataclass │
└──────────┬──────────────────────┘
           │ function_response(s)
           ▼
┌─────────────────────────────────┐
│  ORCHESTRATOR (continued)       │
│  May call more tools or finish  │
│  Writes narrative with [cite:N] │
└──────────┬──────────────────────┘
           │ gemini_text + findings[]
           ▼
┌─────────────────────────────────┐
│  KNOWLEDGE BUS (Gemini 3.1 Pro) │
│  Cross-references findings      │
│  Returns supported/contradicted │
│  Skipped if < 2 findings        │
└──────────┬──────────────────────┘
           │ enriched findings
           ▼
┌─────────────────────────────────┐
│  PYTHON JSON ASSEMBLY           │
│  Wraps text + citations + bus   │
│  Assigns citation IDs           │
│  Returns valid JSON             │
└──────────┬──────────────────────┘
           │
           ▼
{"response": "...text with [cite:N]...", "citations": [...]}
```

## Components

### 1. BaseAgent (`src/agents/base_agent.py`)

Abstract base class defining the contract for all modality agents.

```python
@dataclass
class Finding:
    agent: str       # "ecg", "chest_xray", etc.
    file: str        # "P0001.svg"
    web_path: str    # "/multimodal-data/ecg/P0001.svg"
    summary: str     # "Sinus rhythm 72 bpm, ST depression V4-V6"

class BaseAgent(ABC):
    modality: str    # "ecg"
    data_dir: str    # "ecg"
    file_ext: str    # ".svg"

    @abstractmethod
    def analyze(self, patient_id: str, query: str) -> Finding:
        ...

    def get_file_path(self, patient_id: str) -> str:
        return f"multimodal-data/{self.data_dir}/{patient_id}{self.file_ext}"

    def get_web_path(self, patient_id: str) -> str:
        return f"/multimodal-data/{self.data_dir}/{patient_id}{self.file_ext}"
```

### 2. Seven Stub Agents

Each agent extends `BaseAgent`. The stub implementation loads a hardcoded response from the patient's fixture file.

| Agent Class | Tool Name | Modality | Dir | Ext |
|---|---|---|---|---|
| `ClinicalNotesAgent` | `analyze_clinical_notes` | `clinical_notes` | `clinical-notes` | `.txt` |
| `ChestXrayAgent` | `analyze_chest_xray` | `chest_xray` | `chest-xray` | `.png` |
| `EcgAgent` | `analyze_ecg` | `ecg` | `ecg` | `.svg` |
| `EchoAgent` | `analyze_echo` | `echo` | `echo` | `.mp4` |
| `HeartSoundsAgent` | `analyze_heart_sounds` | `heart_sounds` | `heart-sounds` | `.wav` |
| `LabResultsAgent` | `analyze_lab_results` | `lab_results` | `lab-results` | `.png` |
| `MedicationAgent` | `analyze_medication` | `medication` | `medications` | `.csv` |

Stub `analyze()` implementation (same for all 7). Stub path is resolved relative to the project root using `Path(__file__)` to avoid CWD dependency:
```python
STUBS_DIR = Path(__file__).resolve().parents[2] / "stubs"

def analyze(self, patient_id: str, query: str) -> Finding:
    with open(STUBS_DIR / f"{patient_id}.json") as f:
        stubs = json.load(f)
    data = stubs[self.modality]
    return Finding(
        agent=self.modality,
        file=f"{patient_id}{self.file_ext}",
        web_path=self.get_web_path(patient_id),
        summary=data["summary"]
    )
```

To swap in a real model later, replace the `analyze()` body:
```python
def analyze(self, patient_id: str, query: str) -> Finding:
    file_content = open(self.get_file_path(patient_id)).read()
    result = real_model.predict(file_content, query)
    return Finding(agent=self.modality, ..., summary=result.summary)
```

### 3. Patient Fixture Files (`stubs/P0001.json` ... `stubs/P0010.json`)

One JSON file per patient containing all 7 modality responses. 10 files total (70 stub responses).

```json
{
  "clinical_notes": {
    "summary": "58yo male presenting with 2-3 week history of exertional chest pressure..."
  },
  "chest_xray": {
    "summary": "Mild cardiomegaly with cardiothoracic ratio 0.55..."
  },
  "ecg": {
    "summary": "Normal sinus rhythm at 72 bpm. ST-segment depression 1mm in V4-V6..."
  },
  "echo": {
    "summary": "LVEF estimated at 45% (mildly reduced). Mild hypokinesis lateral wall..."
  },
  "heart_sounds": {
    "summary": "S1 and S2 normal. Grade II/VI systolic murmur at apex..."
  },
  "lab_results": {
    "summary": "Troponin I: 0.04 ng/mL (borderline). BNP: 180 pg/mL (mildly elevated)..."
  },
  "medication": {
    "summary": "Lisinopril 20mg daily, Metformin 1000mg BID, Atorvastatin 40mg daily..."
  }
}
```

Stub responses must be clinically consistent within each patient (e.g., P0001's ECG ST depression aligns with the echo showing reduced LVEF and the clinical notes describing exertional chest pressure).

### 4. Agent Registry

Maps Gemini tool names to agent instances. Defined at module level.

```python
AGENT_REGISTRY = {
    "analyze_clinical_notes": ClinicalNotesAgent(),
    "analyze_chest_xray":     ChestXrayAgent(),
    "analyze_ecg":            EcgAgent(),
    "analyze_echo":           EchoAgent(),
    "analyze_heart_sounds":   HeartSoundsAgent(),
    "analyze_lab_results":    LabResultsAgent(),
    "analyze_medication":     MedicationAgent(),
}
```

### 5. Tool Definitions (`src/tools/definitions.py`)

Seven tool declarations replacing the old three. Each has identical parameters (`patient_id`, `query`) but a modality-specific description that guides Gemini's tool selection:

| Tool Name | Description |
|---|---|
| `analyze_clinical_notes` | "Extract key findings from clinical notes including diagnoses, symptoms, history, and clinical relationships." |
| `analyze_chest_xray` | "Analyze chest X-ray image for thoracic pathologies including cardiac silhouette, lung fields, mediastinum, and bony structures." |
| `analyze_ecg` | "Analyze 12-lead ECG for rhythm, rate, intervals, axis, ST/T-wave changes, and conduction abnormalities." |
| `analyze_echo` | "Analyze echocardiogram video for LV function, wall motion, valvular assessment, and pericardial evaluation." |
| `analyze_heart_sounds` | "Analyze heart auscultation audio for S1/S2 quality, murmurs, gallops, rubs, and extra heart sounds." |
| `analyze_lab_results` | "Analyze laboratory results for abnormal values, clinically significant trends, and critical findings." |
| `analyze_medication` | "Analyze medication regimen for drug list, interactions, contraindications, and therapeutic adequacy." |

Parameter schema (identical for all 7):
```python
{
    "name": "analyze_ecg",  # varies per tool
    "description": "...",   # from table above
    "parameters": {
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "Patient identifier (e.g., 'P0001')"
            },
            "query": {
                "type": "string",
                "description": "Clinical question or focus area for the analysis"
            }
        },
        "required": ["patient_id", "query"]
    }
}
```

### 6. Knowledge Bus (`src/agents/knowledge_bus.py`)

Separate Gemini 3.1 Pro call that cross-references findings.

**Input:** List of findings + patient info.

**Output:** Dict mapping agent name to `{supported_by: [...], contradicted_by: [...]}`.

Each entry in `supported_by` / `contradicted_by`:
```json
{
  "agent": "echo",
  "finding": "LVEF 45%",
  "reason": "Reduced EF consistent with ischemic ST changes"
}
```

Only called when 2+ findings exist. Uses structured JSON output (`response_mime_type: "application/json"`) since this is a standalone call without function calling.

**Prompt template:**
```
You are a medical knowledge cross-referencing system. Given findings from multiple
diagnostic modalities for the same patient, identify clinical correlations.

Patient: {patient_name} ({patient_id}), {age}{sex}, Conditions: {conditions}

Findings:
{numbered_findings_list}

For each finding, identify which other findings support or contradict it with
brief clinical reasoning. Return JSON matching this exact schema.
```

**Response schema:**
```python
response_schema = {
    "type": "object",
    "properties": {
        "<agent_name>": {
            "type": "object",
            "properties": {
                "supported_by": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string"},
                            "finding": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["agent", "finding", "reason"]
                    }
                },
                "contradicted_by": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string"},
                            "finding": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["agent", "finding", "reason"]
                    }
                }
            }
        }
    }
}
```

### 7. Orchestrator (`src/core/orchestrator.py`)

Rewritten `run_pipeline()`.

**System prompt:**
```
ACTIVE PATIENT: {name} ({patient_id})
Age: {age}  Sex: {sex}  Blood Type: {blood_type}
Allergies: {allergies}
Conditions: {conditions}
Available data:
  clinical_notes: {date}
  chest_xray: {date}
  ecg: {date}
  echo: {date}
  heart_sounds: {date}
  lab_results: {date}
  medication: {date}

You are a medical data analysis orchestrator.

TOOLS (use only when a patient is active and the question requires data analysis):
- analyze_clinical_notes: Extract findings from clinical notes
- analyze_chest_xray: Analyze chest X-ray image
- analyze_ecg: Analyze 12-lead ECG
- analyze_echo: Analyze echocardiogram video
- analyze_heart_sounds: Analyze heart auscultation audio
- analyze_lab_results: Analyze laboratory results
- analyze_medication: Analyze medication regimen

Call the tools relevant to the user's question. You may call multiple tools in
a single response when the question spans multiple modalities.

Only call tools for modalities listed in "Available data" above.

CITATION FORMAT:
After receiving tool results, write a clinical narrative referencing each finding
using [cite:N] where N matches the order tools were called (first tool result =
[cite:1], second = [cite:2], etc.). Every finding must be cited at least once.
Do NOT output JSON — write natural text with [cite:N] tokens only.

When no patient is active or the question is general, respond directly without tools.
```

**Parallel tool call handling — pipeline pseudocode:**
```python
def run_pipeline(query, history, patient_id, patient_info):
    client = create_client()
    system_prompt = build_system_prompt(patient_id, patient_info)
    contents = build_contents(history, query)
    config = create_config(tools, system_prompt)
    findings = []

    response = client.models.generate_content(
        model="gemini-3.1-pro", contents=contents, config=config)

    # Tool loop — handles both parallel and sequential calls
    while has_function_calls(response):
        # Extract ALL function calls from this response
        tool_calls = [
            part.function_call
            for part in response.candidates[-1].content.parts
            if part.function_call
        ]

        # Execute each and collect findings
        function_responses = []
        for tc in tool_calls:
            agent = AGENT_REGISTRY[tc.name]
            log_tool_call(tc.name, tc.args)

            finding = agent.analyze(
                patient_id=tc.args["patient_id"],
                query=tc.args["query"]
            )
            findings.append(finding)
            log_tool_result(finding.summary)

            function_responses.append(
                Part.from_function_response(
                    name=tc.name,
                    response={"summary": finding.summary}
                )
            )

        # Append model's response, then ALL function responses in one message
        contents.append(response.candidates[-1].content)
        contents.append(Content(role="user", parts=function_responses))

        response = client.models.generate_content(
            model="gemini-3.1-pro", contents=contents, config=config)

    # Final text
    gemini_text = response.candidates[-1].content.parts[-1].text
    log_assistant(gemini_text)

    # Knowledge bus (if 2+ findings)
    if len(findings) >= 2:
        knowledge_bus = build_knowledge_bus(findings, patient_info)
    else:
        knowledge_bus = {}

    # Assemble JSON or return plain text
    if findings:
        return assemble_response(gemini_text, findings, knowledge_bus)
    else:
        return gemini_text
```

**Post-loop processing:**
- Extracts Gemini's narrative text
- Runs knowledge bus if 2+ findings
- Calls `assemble_response()` to build final JSON
- Falls back to plain text if no tools were called (general questions)

### 8. Response Assembly

Deterministic Python — no LLM involved:

```python
def assemble_response(gemini_text, findings, knowledge_bus):
    citations = []
    for i, finding in enumerate(findings):
        citations.append({
            "id": str(i + 1),
            "agent": finding.agent,
            "file": finding.file,
            "web_path": finding.web_path,
            "summary": finding.summary,
            "knowledge_bus": knowledge_bus.get(finding.agent, {
                "supported_by": [], "contradicted_by": []
            })
        })
    return json.dumps({"response": gemini_text, "citations": citations})
```

## File Changes

### New Files
| File | Purpose |
|---|---|
| `src/agents/base_agent.py` | BaseAgent ABC + Finding dataclass |
| `src/agents/clinical_notes_agent.py` | Clinical notes stub agent |
| `src/agents/chest_xray_agent.py` | Chest X-ray stub agent |
| `src/agents/ecg_agent.py` | ECG stub agent |
| `src/agents/echo_agent.py` | Echo stub agent |
| `src/agents/heart_sounds_agent.py` | Heart sounds stub agent |
| `src/agents/lab_results_agent.py` | Lab results stub agent |
| `src/agents/medication_agent.py` | Medication stub agent |
| `src/agents/knowledge_bus.py` | Knowledge bus cross-referencing |
| `stubs/P0001.json` ... `stubs/P0010.json` | 10 patient fixture files |

### Rewritten Files
| File | Changes |
|---|---|
| `src/core/orchestrator.py` | New pipeline with parallel tool calls, findings collection, knowledge bus, JSON assembly |
| `src/agents/prompts.py` | New system instruction with 7 tools + citation format |
| `src/tools/definitions.py` | 7 new tool declarations replacing old 3 |

### Minor Updates
| File | Changes |
|---|---|
| `src/utils/logging.py` | Add 7 new tool names to `header_map` |
| `src/core/gemini_client.py` | Update model name to `gemini-3.1-pro` |

### Deleted Files
| File | Reason |
|---|---|
| `src/agents/executors.py` | Code generation agents replaced by modality agents |

### Dead Code Removal
| Item | Location | Reason |
|---|---|---|
| `write_agent_summary()` | `src/utils/logging.py` | No agents generate code or write summaries anymore |
| `read_agent_summary()` | `src/utils/logging.py` | Same as above |
| `read_all_summaries()` | `src/utils/logging.py` | Same as above |
| `shared_knowledge.xml` | Project root | XML persistence no longer used |

## Edge Cases

| Scenario | Behavior |
|---|---|
| No patient active + general question | Gemini responds directly, no tools, plain text |
| Patient active + single modality | 1 tool called, 1 citation, knowledge bus skipped |
| Patient active + broad question | Multiple parallel tools, knowledge bus runs |
| Follow-up question | Works via conversation history |
| Conversational question with patient | Gemini answers directly, no tools |
| Sequential tool calls | Loop handles naturally, keeps going until no more calls |

## Model

All Gemini calls use `gemini-3.1-pro` — orchestrator, knowledge bus, and any future real-model agents that need LLM support.

## What This Does NOT Change

- Frontend code (already built for this format)
- Server endpoints (POST /api/chat, patient APIs, pin APIs, WebSocket)
- Session management
- Multimodal data files
- Patient info files
