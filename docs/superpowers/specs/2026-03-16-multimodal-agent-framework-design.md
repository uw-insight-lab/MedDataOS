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

Stub `analyze()` implementation (same for all 7):
```python
def analyze(self, patient_id: str, query: str) -> Finding:
    with open(f"stubs/{patient_id}.json") as f:
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

Seven tool declarations replacing the old three. Each has identical parameters:

```python
{
    "name": "analyze_ecg",
    "description": "Analyze 12-lead ECG for a patient. Returns rhythm, rate, intervals, axis, ST/T changes, and abnormalities.",
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

Each tool has a modality-specific `description` explaining what it analyzes and returns.

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

Only called when 2+ findings exist. Uses structured JSON output (response_mime_type) since this is a standalone call without function calling.

### 7. Orchestrator (`src/core/orchestrator.py`)

Rewritten `run_pipeline()` with:

**Parallel tool call handling:**
- Iterates all `parts` in Gemini's response to find function calls
- Executes each agent, collects findings
- Sends all function responses back in a single Content message

**System prompt construction:**
- Patient context block (demographics + available data modalities with dates)
- Role & tools description
- Citation format instructions (use `[cite:N]`, don't output JSON)

**Post-loop processing:**
- Extracts Gemini's narrative text
- Runs knowledge bus if 2+ findings
- Calls `assemble_response()` to build final JSON
- Falls back to plain text if no tools were called

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
