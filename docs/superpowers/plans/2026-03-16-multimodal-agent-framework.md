# Multimodal Medical Agent Framework Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing 3-tool backend with a 7-agent multimodal medical analysis framework using hardcoded stub responses per patient, with a clean interface for swapping real models later.

**Architecture:** Pipeline with 3 stages — Gemini 3.1 Pro orchestrator with function calling decides which modality agents to invoke, a separate knowledge bus Gemini call cross-references findings, and deterministic Python assembles the final citation JSON. Seven stub agents implement a BaseAgent interface and return pre-written patient-specific findings from fixture files.

**Tech Stack:** Python 3, FastAPI (existing), Google Gemini API (`google-genai`), pytest

**Spec:** `docs/superpowers/specs/2026-03-16-multimodal-agent-framework-design.md`

---

## Chunk 1: Foundation — BaseAgent, Finding, and First Stub Agent

### Task 1: Create BaseAgent and Finding

**Files:**
- Create: `src/agents/base_agent.py`
- Create: `tests/agents/test_base_agent.py`

- [ ] **Step 1: Write test for Finding dataclass**

```python
# tests/agents/test_base_agent.py
from src.agents.base_agent import Finding

def test_finding_fields():
    f = Finding(agent="ecg", file="P0001.svg", web_path="/multimodal-data/ecg/P0001.svg", summary="Normal sinus rhythm")
    assert f.agent == "ecg"
    assert f.file == "P0001.svg"
    assert f.web_path == "/multimodal-data/ecg/P0001.svg"
    assert f.summary == "Normal sinus rhythm"
```

- [ ] **Step 2: Write test for BaseAgent contract**

```python
# tests/agents/test_base_agent.py (append)
from src.agents.base_agent import BaseAgent, Finding

class DummyAgent(BaseAgent):
    modality = "test"
    data_dir = "test-dir"
    file_ext = ".txt"

    def analyze(self, patient_id: str, query: str) -> Finding:
        return Finding(agent=self.modality, file=f"{patient_id}{self.file_ext}",
                       web_path=self.get_web_path(patient_id), summary="test summary")

def test_base_agent_get_file_path():
    agent = DummyAgent()
    assert agent.get_file_path("P0001") == "multimodal-data/test-dir/P0001.txt"

def test_base_agent_get_web_path():
    agent = DummyAgent()
    assert agent.get_web_path("P0001") == "/multimodal-data/test-dir/P0001.txt"

def test_base_agent_analyze():
    agent = DummyAgent()
    finding = agent.analyze("P0001", "test query")
    assert finding.agent == "test"
    assert finding.file == "P0001.txt"
    assert finding.summary == "test summary"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_base_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.base_agent'`

- [ ] **Step 4: Implement BaseAgent and Finding**

```python
# src/agents/base_agent.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Finding:
    agent: str
    file: str
    web_path: str
    summary: str


class BaseAgent(ABC):
    modality: str
    data_dir: str
    file_ext: str

    @abstractmethod
    def analyze(self, patient_id: str, query: str) -> Finding:
        ...

    def get_file_path(self, patient_id: str) -> str:
        return f"multimodal-data/{self.data_dir}/{patient_id}{self.file_ext}"

    def get_web_path(self, patient_id: str) -> str:
        return f"/multimodal-data/{self.data_dir}/{patient_id}{self.file_ext}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_base_agent.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/agents/base_agent.py tests/agents/test_base_agent.py
git commit -m "feat: add BaseAgent ABC and Finding dataclass"
```

---

### Task 2: Create first patient fixture file (P0001) and first stub agent (EcgAgent)

**Files:**
- Create: `stubs/P0001.json`
- Create: `src/agents/ecg_agent.py`
- Create: `tests/agents/test_ecg_agent.py`

- [ ] **Step 1: Create P0001 fixture file**

Create `stubs/P0001.json` with clinically consistent responses for patient James Carter (58M, HTN, DM2, hyperlipidemia, asthma, presenting with exertional chest pressure):

```json
{
  "clinical_notes": {
    "summary": "58yo male presenting with 2-3 week history of exertional substernal chest pressure, 4/10, triggered by moderate activity (stairs, brisk walking), resolving within 5 minutes of rest. Associated mild dyspnea on exertion. Increased fatigue over past month. No rest pain, palpitations, syncope, or diaphoresis. PMH: hypertension, type 2 diabetes, hyperlipidemia, asthma. Medication adherent. No prior episodes of this severity."
  },
  "chest_xray": {
    "summary": "Mild cardiomegaly with cardiothoracic ratio 0.55. Lung fields clear bilaterally, no infiltrates, consolidation, or pleural effusions. Mediastinal contours normal. Aortic knob mildly prominent consistent with age and hypertension. No acute bony abnormalities."
  },
  "ecg": {
    "summary": "Normal sinus rhythm at 72 bpm. PR interval 160ms (normal). QRS duration 88ms (normal). Normal axis. ST-segment depression of 1mm in leads V4-V6 suggesting lateral ischemia. No pathological Q waves. T-wave flattening in leads I and aVL. QTc 420ms (normal)."
  },
  "echo": {
    "summary": "Left ventricular ejection fraction estimated at 45% (mildly reduced). Mild hypokinesis of the lateral wall. Left atrial size normal. No significant valvular disease — trace mitral regurgitation. Normal right ventricular size and function. No pericardial effusion. Diastolic function grade I (impaired relaxation)."
  },
  "heart_sounds": {
    "summary": "S1 and S2 normal intensity and splitting. Grade II/VI systolic murmur at the apex, non-radiating, consistent with trace mitral regurgitation. No diastolic murmurs. No S3 gallop. No S4 gallop. No pericardial rubs or clicks detected. Heart rate regular at 72 bpm."
  },
  "lab_results": {
    "summary": "Troponin I: 0.04 ng/mL (borderline, normal <0.03). BNP: 180 pg/mL (mildly elevated, normal <100). HbA1c: 7.2% (above target of <7%). Fasting glucose: 148 mg/dL (elevated). Total cholesterol: 228 mg/dL, LDL: 142 mg/dL (elevated), HDL: 38 mg/dL (low), triglycerides: 198 mg/dL (elevated). Creatinine: 1.3 mg/dL, eGFR: 68 mL/min (mildly reduced). CBC within normal limits. TSH: 2.1 mIU/L (normal)."
  },
  "medication": {
    "summary": "Active medications: Lisinopril 20mg daily (ACE inhibitor for HTN), Metformin 1000mg BID (diabetes), Atorvastatin 40mg daily (hyperlipidemia), Albuterol inhaler PRN (asthma), Aspirin 81mg daily (cardioprotective). No drug-drug interactions flagged. Note: Atorvastatin dose may be subtherapeutic given LDL 142 mg/dL — consider uptitration to 80mg. Penicillin allergy documented. No contraindications identified."
  }
}
```

- [ ] **Step 2: Write test for EcgAgent**

```python
# tests/agents/test_ecg_agent.py
from src.agents.ecg_agent import EcgAgent

def test_ecg_agent_properties():
    agent = EcgAgent()
    assert agent.modality == "ecg"
    assert agent.data_dir == "ecg"
    assert agent.file_ext == ".svg"

def test_ecg_agent_analyze_p0001():
    agent = EcgAgent()
    finding = agent.analyze("P0001", "cardiac workup")
    assert finding.agent == "ecg"
    assert finding.file == "P0001.svg"
    assert finding.web_path == "/multimodal-data/ecg/P0001.svg"
    assert "sinus rhythm" in finding.summary.lower()
    assert "72 bpm" in finding.summary

def test_ecg_agent_analyze_returns_finding_type():
    from src.agents.base_agent import Finding
    agent = EcgAgent()
    finding = agent.analyze("P0001", "anything")
    assert isinstance(finding, Finding)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_ecg_agent.py -v`
Expected: FAIL

- [ ] **Step 4: Implement EcgAgent**

```python
# src/agents/ecg_agent.py
import json
from pathlib import Path
from src.agents.base_agent import BaseAgent, Finding

STUBS_DIR = Path(__file__).resolve().parents[2] / "stubs"


class EcgAgent(BaseAgent):
    modality = "ecg"
    data_dir = "ecg"
    file_ext = ".svg"

    def analyze(self, patient_id: str, query: str) -> Finding:
        with open(STUBS_DIR / f"{patient_id}.json") as f:
            stubs = json.load(f)
        data = stubs[self.modality]
        return Finding(
            agent=self.modality,
            file=f"{patient_id}{self.file_ext}",
            web_path=self.get_web_path(patient_id),
            summary=data["summary"],
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_ecg_agent.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add stubs/P0001.json src/agents/ecg_agent.py tests/agents/test_ecg_agent.py
git commit -m "feat: add EcgAgent stub and P0001 fixture"
```

---

## Chunk 2: Remaining 6 Stub Agents and 9 Patient Fixtures

### Task 3: Create remaining 6 stub agents

**Files:**
- Create: `src/agents/clinical_notes_agent.py`
- Create: `src/agents/chest_xray_agent.py`
- Create: `src/agents/echo_agent.py`
- Create: `src/agents/heart_sounds_agent.py`
- Create: `src/agents/lab_results_agent.py`
- Create: `src/agents/medication_agent.py`
- Create: `tests/agents/test_stub_agents.py`

Each agent follows the exact same pattern as EcgAgent. Only the class attributes differ.

- [ ] **Step 1: Write tests for all 6 agents**

```python
# tests/agents/test_stub_agents.py
import pytest
from src.agents.base_agent import Finding
from src.agents.clinical_notes_agent import ClinicalNotesAgent
from src.agents.chest_xray_agent import ChestXrayAgent
from src.agents.echo_agent import EchoAgent
from src.agents.heart_sounds_agent import HeartSoundsAgent
from src.agents.lab_results_agent import LabResultsAgent
from src.agents.medication_agent import MedicationAgent

AGENT_SPECS = [
    (ClinicalNotesAgent, "clinical_notes", "clinical-notes", ".txt"),
    (ChestXrayAgent, "chest_xray", "chest-xray", ".png"),
    (EchoAgent, "echo", "echo", ".mp4"),
    (HeartSoundsAgent, "heart_sounds", "heart-sounds", ".wav"),
    (LabResultsAgent, "lab_results", "lab-results", ".png"),
    (MedicationAgent, "medication", "medications", ".csv"),
]

@pytest.mark.parametrize("cls,modality,data_dir,file_ext", AGENT_SPECS)
def test_agent_properties(cls, modality, data_dir, file_ext):
    agent = cls()
    assert agent.modality == modality
    assert agent.data_dir == data_dir
    assert agent.file_ext == file_ext

@pytest.mark.parametrize("cls,modality,data_dir,file_ext", AGENT_SPECS)
def test_agent_analyze_p0001(cls, modality, data_dir, file_ext):
    agent = cls()
    finding = agent.analyze("P0001", "test query")
    assert isinstance(finding, Finding)
    assert finding.agent == modality
    assert finding.file == f"P0001{file_ext}"
    assert finding.web_path == f"/multimodal-data/{data_dir}/P0001{file_ext}"
    assert len(finding.summary) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_stub_agents.py -v`
Expected: FAIL — import errors

- [ ] **Step 3: Implement all 6 agents**

Each follows the identical pattern. Example for ClinicalNotesAgent:

```python
# src/agents/clinical_notes_agent.py
import json
from pathlib import Path
from src.agents.base_agent import BaseAgent, Finding

STUBS_DIR = Path(__file__).resolve().parents[2] / "stubs"


class ClinicalNotesAgent(BaseAgent):
    modality = "clinical_notes"
    data_dir = "clinical-notes"
    file_ext = ".txt"

    def analyze(self, patient_id: str, query: str) -> Finding:
        with open(STUBS_DIR / f"{patient_id}.json") as f:
            stubs = json.load(f)
        data = stubs[self.modality]
        return Finding(
            agent=self.modality,
            file=f"{patient_id}{self.file_ext}",
            web_path=self.get_web_path(patient_id),
            summary=data["summary"],
        )
```

Remaining agents use the same code with these attributes:

| File | Class | modality | data_dir | file_ext |
|---|---|---|---|---|
| `chest_xray_agent.py` | `ChestXrayAgent` | `chest_xray` | `chest-xray` | `.png` |
| `echo_agent.py` | `EchoAgent` | `echo` | `echo` | `.mp4` |
| `heart_sounds_agent.py` | `HeartSoundsAgent` | `heart_sounds` | `heart-sounds` | `.wav` |
| `lab_results_agent.py` | `LabResultsAgent` | `lab_results` | `lab-results` | `.png` |
| `medication_agent.py` | `MedicationAgent` | `medication` | `medications` | `.csv` |

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_stub_agents.py -v`
Expected: 12 tests PASS (2 per agent × 6 agents)

- [ ] **Step 5: Commit**

```bash
git add src/agents/clinical_notes_agent.py src/agents/chest_xray_agent.py \
        src/agents/echo_agent.py src/agents/heart_sounds_agent.py \
        src/agents/lab_results_agent.py src/agents/medication_agent.py \
        tests/agents/test_stub_agents.py
git commit -m "feat: add remaining 6 stub agents"
```

---

### Task 4: Create remaining 9 patient fixture files (P0002–P0010)

**Files:**
- Create: `stubs/P0002.json` through `stubs/P0010.json`
- Create: `tests/agents/test_fixtures.py`

Each fixture must be clinically consistent with the patient's demographics, conditions, and clinical notes. The implementer should use the patient info from `multimodal-data/patient-info/P*.json` and clinical notes from `multimodal-data/clinical-notes/P*.txt` as context to write realistic stub summaries.

- [ ] **Step 1: Write test that validates all 10 fixtures exist and have correct structure**

```python
# tests/agents/test_fixtures.py
import json
import pytest
from pathlib import Path

STUBS_DIR = Path(__file__).resolve().parents[2] / "stubs"
REQUIRED_MODALITIES = [
    "clinical_notes", "chest_xray", "ecg", "echo",
    "heart_sounds", "lab_results", "medication"
]
PATIENT_IDS = [f"P{i:04d}" for i in range(1, 11)]

@pytest.mark.parametrize("patient_id", PATIENT_IDS)
def test_fixture_exists_and_valid(patient_id):
    path = STUBS_DIR / f"{patient_id}.json"
    assert path.exists(), f"Missing fixture: {path}"
    with open(path) as f:
        data = json.load(f)
    for modality in REQUIRED_MODALITIES:
        assert modality in data, f"{patient_id} missing modality: {modality}"
        assert "summary" in data[modality], f"{patient_id}.{modality} missing summary"
        assert len(data[modality]["summary"]) > 20, f"{patient_id}.{modality} summary too short"

@pytest.mark.parametrize("patient_id", PATIENT_IDS)
def test_all_agents_can_load_fixture(patient_id):
    from src.agents.ecg_agent import EcgAgent
    from src.agents.clinical_notes_agent import ClinicalNotesAgent
    from src.agents.chest_xray_agent import ChestXrayAgent
    from src.agents.echo_agent import EchoAgent
    from src.agents.heart_sounds_agent import HeartSoundsAgent
    from src.agents.lab_results_agent import LabResultsAgent
    from src.agents.medication_agent import MedicationAgent

    agents = [EcgAgent(), ClinicalNotesAgent(), ChestXrayAgent(), EchoAgent(),
              HeartSoundsAgent(), LabResultsAgent(), MedicationAgent()]
    for agent in agents:
        finding = agent.analyze(patient_id, "test")
        assert finding.agent == agent.modality
        assert patient_id in finding.file
```

- [ ] **Step 2: Run tests to verify they fail (9 fixtures missing)**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_fixtures.py -v`
Expected: 10 PASS for P0001, 9 FAIL for P0002–P0010

- [ ] **Step 3: Create all 9 fixture files**

Create `stubs/P0002.json` through `stubs/P0010.json`. Each must be clinically consistent with the patient's demographics, conditions, and clinical notes. Read each patient's clinical notes from `multimodal-data/clinical-notes/P*.txt` and patient info from `multimodal-data/patient-info/P*.json`. Each summary should be 1-3 sentences with specific clinical values.

**Full example — P0002 (Maria Lopez, 34F, pneumonia):**

```json
{
  "clinical_notes": {
    "summary": "34yo female presenting with 5-day history of fever (peak 39.2°C), productive cough with purulent sputum, and right-sided pleuritic chest pain. Progressive dyspnea now with minimal exertion. PMH: mild intermittent asthma. SpO2 94% on room air. Crackles and bronchial breath sounds over right lower lobe with dullness to percussion."
  },
  "chest_xray": {
    "summary": "Right lower lobe consolidation with air bronchograms consistent with community-acquired pneumonia. No pleural effusion. Heart size normal. Left lung clear. No pneumothorax."
  },
  "ecg": {
    "summary": "Sinus tachycardia at 112 bpm. Normal axis. PR interval 140ms. QRS 82ms. No ST-segment changes. No T-wave inversions. QTc 390ms. Tachycardia likely secondary to fever and infection."
  },
  "echo": {
    "summary": "Normal left ventricular size and function, LVEF 62%. No wall motion abnormalities. Trivial tricuspid regurgitation. Estimated RVSP 28 mmHg (normal). No pericardial effusion. Normal diastolic function."
  },
  "heart_sounds": {
    "summary": "S1 and S2 normal. Tachycardic rate at 112 bpm. No murmurs, gallops, or rubs detected. No S3 or S4. Heart sounds regular in rhythm despite elevated rate."
  },
  "lab_results": {
    "summary": "WBC: 15.2 x10³/µL (elevated, neutrophil predominance 82%). CRP: 148 mg/L (markedly elevated). Procalcitonin: 1.8 ng/mL (elevated, suggesting bacterial infection). BMP within normal limits. Creatinine 0.8 mg/dL. Lactate 1.4 mmol/L (normal). Blood cultures pending."
  },
  "medication": {
    "summary": "Active medications: Albuterol inhaler PRN (asthma). Initiated: Ceftriaxone 1g IV daily + Azithromycin 500mg IV daily (CAP empiric coverage). Acetaminophen 1g q6h PRN (fever). IV normal saline for hydration. No drug allergies. No significant drug interactions."
  }
}
```

**Full example — P0004 (Dorothy Williams, 72F, acute decompensated heart failure):**

```json
{
  "clinical_notes": {
    "summary": "72yo female with known HFrEF (last EF 30%), chronic AFib, CKD stage 3, and HTN presenting with progressive dyspnea at rest over past week. Bilateral lower extremity edema and 4kg weight gain over 10 days. Three-pillow orthopnea, 2 episodes of PND this week. Decreased urine output. Dietary indiscretion 2 weeks ago. Allergy to ACE inhibitors (angioedema with lisinopril)."
  },
  "chest_xray": {
    "summary": "Cardiomegaly with cardiothoracic ratio 0.62. Bilateral pulmonary vascular congestion with cephalization of flow. Bilateral pleural effusions, small to moderate. Kerley B lines present. No focal consolidation."
  },
  "ecg": {
    "summary": "Atrial fibrillation with controlled ventricular rate at 88 bpm. Left axis deviation. Low voltage in limb leads. Non-specific ST-T wave changes in lateral leads. QRS 110ms. No acute ST elevation or depression. Prior pattern unchanged."
  },
  "echo": {
    "summary": "Severely reduced LVEF estimated at 25% (decreased from 30% six months ago). Global hypokinesis with akinesis of inferior wall. Moderate mitral regurgitation (functional). Left atrium moderately dilated at 4.6cm. Elevated E/e' ratio of 18 suggesting elevated filling pressures. Mild tricuspid regurgitation with RVSP 48 mmHg."
  },
  "heart_sounds": {
    "summary": "Irregularly irregular rhythm consistent with atrial fibrillation. S3 gallop present. Grade III/VI holosystolic murmur at apex radiating to axilla consistent with mitral regurgitation. Variable intensity of S1. No pericardial rub."
  },
  "lab_results": {
    "summary": "BNP: 1,840 pg/mL (markedly elevated). Troponin I: 0.02 ng/mL (normal). Creatinine: 1.8 mg/dL (elevated from baseline 1.4), eGFR: 32 mL/min (worsening CKD). Sodium: 131 mEq/L (hyponatremia). Potassium: 4.8 mEq/L. Hemoglobin: 10.8 g/dL (mild anemia). INR: not on warfarin (on apixaban)."
  },
  "medication": {
    "summary": "Active medications: Furosemide 40mg BID (diuretic), Carvedilol 12.5mg BID (beta-blocker), Losartan 50mg daily (ARB — switched from lisinopril due to angioedema), Apixaban 5mg BID (anticoagulation for AFib). ACE inhibitor allergy documented. Consider IV diuretic conversion and dose escalation. Carvedilol may need dose reduction if hypotensive."
  }
}
```

**Remaining patients — create using the same pattern. Key clinical context for each:**

| Patient | Key Focus | Notes for Fixture |
|---|---|---|
| P0003 Robert Chen, 45M | Wellness exam, essentially normal | All findings should be normal/unremarkable. Mild deconditioning only. |
| P0005 Aisha Patel, 28F | Benign palpitations | Normal cardiac workup. Consider sinus tachycardia or PACs on ECG. No structural disease. |
| P0006 Frank Morrison, 67M | COPD exacerbation | Hyperinflated lungs on CXR. Right heart strain possible on echo. Elevated WBC. |
| P0007 Susan Nakamura, 63F | New-onset AFib | Irregularly irregular ECG. May have mild LA dilation on echo. TSH should be checked. |
| P0008 David Okafor, 52M | Poorly controlled DM2 | HbA1c elevated. LVH possible on ECG/echo. Proteinuria in labs. Multiple DM meds. |
| P0009 Harold Jensen, 79M | Severe aortic stenosis | Crescendo-decrescendo murmur. Calcified aortic valve on echo with high gradient. LVH on ECG. |
| P0010 Lisa Fernandez, 41F | Post-STEMI follow-up | Anterior wall motion abnormality on echo. DAPT on medication list. Improving LVEF. |

Read each patient's full clinical notes at `multimodal-data/clinical-notes/P*.txt` for detailed clinical context when writing each fixture.

- [ ] **Step 4: Run tests to verify all pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_fixtures.py -v`
Expected: 20 tests PASS (10 structure + 10 agent loading)

- [ ] **Step 5: Commit**

```bash
git add stubs/P0002.json stubs/P0003.json stubs/P0004.json stubs/P0005.json \
        stubs/P0006.json stubs/P0007.json stubs/P0008.json stubs/P0009.json \
        stubs/P0010.json tests/agents/test_fixtures.py
git commit -m "feat: add patient fixture files P0002-P0010"
```

---

## Chunk 3: Tool Definitions and Prompts

### Task 5: Rewrite tool definitions

**Files:**
- Rewrite: `src/tools/definitions.py`
- Create: `tests/tools/test_definitions.py`

- [ ] **Step 1: Write test for tool definitions**

```python
# tests/tools/test_definitions.py
import pytest
from src.tools.definitions import tools, TOOL_DECLARATIONS

EXPECTED_TOOLS = [
    "analyze_clinical_notes",
    "analyze_chest_xray",
    "analyze_ecg",
    "analyze_echo",
    "analyze_heart_sounds",
    "analyze_lab_results",
    "analyze_medication",
]

def test_all_seven_tools_declared():
    names = [t["name"] for t in TOOL_DECLARATIONS]
    for expected in EXPECTED_TOOLS:
        assert expected in names, f"Missing tool: {expected}"

def test_each_tool_has_patient_id_and_query():
    for tool_def in TOOL_DECLARATIONS:
        props = tool_def["parameters"]["properties"]
        assert "patient_id" in props, f"{tool_def['name']} missing patient_id"
        assert "query" in props, f"{tool_def['name']} missing query"
        assert tool_def["parameters"]["required"] == ["patient_id", "query"]

def test_tools_object_is_gemini_tool():
    from google.genai import types
    assert isinstance(tools, types.Tool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/tools/test_definitions.py -v`
Expected: FAIL — old tool definitions don't match

- [ ] **Step 3: Rewrite definitions.py**

```python
# src/tools/definitions.py
from google.genai import types

def _make_tool(name: str, description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient identifier (e.g., 'P0001')",
                },
                "query": {
                    "type": "string",
                    "description": "Clinical question or focus area for the analysis",
                },
            },
            "required": ["patient_id", "query"],
        },
    }

TOOL_DECLARATIONS = [
    _make_tool("analyze_clinical_notes",
               "Extract key findings from clinical notes including diagnoses, symptoms, history, and clinical relationships."),
    _make_tool("analyze_chest_xray",
               "Analyze chest X-ray image for thoracic pathologies including cardiac silhouette, lung fields, mediastinum, and bony structures."),
    _make_tool("analyze_ecg",
               "Analyze 12-lead ECG for rhythm, rate, intervals, axis, ST/T-wave changes, and conduction abnormalities."),
    _make_tool("analyze_echo",
               "Analyze echocardiogram video for LV function, wall motion, valvular assessment, and pericardial evaluation."),
    _make_tool("analyze_heart_sounds",
               "Analyze heart auscultation audio for S1/S2 quality, murmurs, gallops, rubs, and extra heart sounds."),
    _make_tool("analyze_lab_results",
               "Analyze laboratory results for abnormal values, clinically significant trends, and critical findings."),
    _make_tool("analyze_medication",
               "Analyze medication regimen for drug list, interactions, contraindications, and therapeutic adequacy."),
]

tools = types.Tool(function_declarations=TOOL_DECLARATIONS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/tools/test_definitions.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/definitions.py tests/tools/test_definitions.py
git commit -m "feat: replace old tool definitions with 7 modality tools"
```

---

### Task 6: Rewrite prompts.py

**Files:**
- Rewrite: `src/agents/prompts.py`
- Create: `tests/agents/test_prompts.py`

- [ ] **Step 1: Write test for system prompt builder**

```python
# tests/agents/test_prompts.py
from src.agents.prompts import build_system_prompt, BASE_SYSTEM_INSTRUCTION, KNOWLEDGE_BUS_PROMPT_TEMPLATE

def test_base_instruction_has_tools():
    assert "analyze_clinical_notes" in BASE_SYSTEM_INSTRUCTION
    assert "analyze_ecg" in BASE_SYSTEM_INSTRUCTION
    assert "[cite:N]" in BASE_SYSTEM_INSTRUCTION

def test_build_system_prompt_with_patient():
    patient_info = {
        "name": "James Carter",
        "age": 58,
        "sex": "M",
        "blood_type": "A+",
        "allergies": ["Penicillin"],
        "conditions": ["Hypertension", "Type 2 Diabetes"],
        "data_dates": {"chest-xray": "2026-01-15", "ecg": "2026-02-03"},
    }
    prompt = build_system_prompt("P0001", patient_info)
    assert "James Carter" in prompt
    assert "P0001" in prompt
    assert "Penicillin" in prompt
    assert "chest-xray: 2026-01-15" in prompt
    assert "ecg: 2026-02-03" in prompt
    assert BASE_SYSTEM_INSTRUCTION in prompt

def test_build_system_prompt_without_patient():
    prompt = build_system_prompt(None, None)
    assert prompt == BASE_SYSTEM_INSTRUCTION

def test_knowledge_bus_prompt_template_has_placeholders():
    assert "{patient_name}" in KNOWLEDGE_BUS_PROMPT_TEMPLATE
    assert "{patient_id}" in KNOWLEDGE_BUS_PROMPT_TEMPLATE
    assert "{numbered_findings_list}" in KNOWLEDGE_BUS_PROMPT_TEMPLATE
    assert "{conditions}" in KNOWLEDGE_BUS_PROMPT_TEMPLATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_prompts.py -v`
Expected: FAIL

- [ ] **Step 3: Rewrite prompts.py**

```python
# src/agents/prompts.py

BASE_SYSTEM_INSTRUCTION = """You are a medical data analysis orchestrator.

TOOLS (use only when a patient is active and the question requires data analysis):
- analyze_clinical_notes: Extract findings from clinical notes
- analyze_chest_xray: Analyze chest X-ray image
- analyze_ecg: Analyze 12-lead ECG
- analyze_echo: Analyze echocardiogram video
- analyze_heart_sounds: Analyze heart auscultation audio
- analyze_lab_results: Analyze laboratory results
- analyze_medication: Analyze medication regimen

Call the tools relevant to the user's question. You may call multiple tools in a single response when the question spans multiple modalities.

Only call tools for modalities listed in "Available data" above.

CITATION FORMAT:
After receiving tool results, write a clinical narrative referencing each finding using [cite:N] where N matches the order tools were called (first tool result = [cite:1], second = [cite:2], etc.). Every finding must be cited at least once.
Do NOT output JSON — write natural text with [cite:N] tokens only.

When no patient is active or the question is general, respond directly without tools."""


KNOWLEDGE_BUS_PROMPT_TEMPLATE = """You are a medical knowledge cross-referencing system. Given findings from multiple diagnostic modalities for the same patient, identify clinical correlations.

Patient: {patient_name} ({patient_id}), {age}{sex}, Conditions: {conditions}

Findings:
{numbered_findings_list}

For each finding, identify which other findings support or contradict it with brief clinical reasoning. Return JSON matching the schema provided."""


def build_system_prompt(patient_id: str | None, patient_info: dict | None) -> str:
    if not patient_id or not patient_info:
        return BASE_SYSTEM_INSTRUCTION

    name = patient_info.get("name", patient_id)
    age = patient_info.get("age", "?")
    sex = patient_info.get("sex", "?")
    blood_type = patient_info.get("blood_type", "N/A")
    allergies = ", ".join(patient_info.get("allergies", [])) or "None"
    conditions = ", ".join(patient_info.get("conditions", [])) or "None"

    data_dates = patient_info.get("data_dates", {})
    modality_lines = "\n".join(f"  {k}: {v}" for k, v in data_dates.items())

    patient_block = (
        f"ACTIVE PATIENT: {name} ({patient_id})\n"
        f"Age: {age}  Sex: {sex}  Blood Type: {blood_type}\n"
        f"Allergies: {allergies}\n"
        f"Conditions: {conditions}\n"
        f"Available data:\n{modality_lines}\n\n"
    )

    return patient_block + BASE_SYSTEM_INSTRUCTION
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_prompts.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/prompts.py tests/agents/test_prompts.py
git commit -m "feat: rewrite prompts with system prompt builder and knowledge bus template"
```

---

## Chunk 4: Knowledge Bus

### Task 7: Implement knowledge bus

**Files:**
- Create: `src/agents/knowledge_bus.py`
- Create: `tests/agents/test_knowledge_bus.py`

- [ ] **Step 1: Write test for knowledge bus**

```python
# tests/agents/test_knowledge_bus.py
import json
from unittest.mock import patch, MagicMock
from src.agents.base_agent import Finding
from src.agents.knowledge_bus import build_knowledge_bus, _build_knowledge_bus_prompt

def test_build_prompt():
    findings = [
        Finding(agent="ecg", file="P0001.svg", web_path="/x", summary="ST depression V4-V6"),
        Finding(agent="echo", file="P0001.mp4", web_path="/y", summary="LVEF 45%"),
    ]
    patient_info = {"name": "James Carter", "age": 58, "sex": "M", "conditions": ["HTN"]}
    prompt = _build_knowledge_bus_prompt(findings, "P0001", patient_info)
    assert "James Carter" in prompt
    assert "ST depression" in prompt
    assert "LVEF 45%" in prompt
    assert "1. ecg:" in prompt
    assert "2. echo:" in prompt

@patch("src.agents.knowledge_bus.create_client")
def test_build_knowledge_bus_calls_gemini(mock_create_client):
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client

    # Simulate Gemini returning valid knowledge bus JSON
    bus_response = {
        "ecg": {
            "supported_by": [{"agent": "echo", "finding": "LVEF 45%", "reason": "consistent"}],
            "contradicted_by": [],
        },
        "echo": {
            "supported_by": [{"agent": "ecg", "finding": "ST depression", "reason": "consistent"}],
            "contradicted_by": [],
        },
    }
    mock_response = MagicMock()
    mock_response.text = json.dumps(bus_response)
    mock_client.models.generate_content.return_value = mock_response

    findings = [
        Finding(agent="ecg", file="P0001.svg", web_path="/x", summary="ST depression V4-V6"),
        Finding(agent="echo", file="P0001.mp4", web_path="/y", summary="LVEF 45%"),
    ]
    patient_info = {"name": "James Carter", "age": 58, "sex": "M", "conditions": ["HTN"]}

    result = build_knowledge_bus(findings, "P0001", patient_info)
    assert "ecg" in result
    assert "echo" in result
    assert len(result["ecg"]["supported_by"]) == 1
    mock_client.models.generate_content.assert_called_once()

@patch("src.agents.knowledge_bus.create_client")
def test_build_knowledge_bus_handles_malformed_response(mock_create_client):
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "not json"
    mock_client.models.generate_content.return_value = mock_response

    findings = [
        Finding(agent="ecg", file="P0001.svg", web_path="/x", summary="ST depression"),
        Finding(agent="echo", file="P0001.mp4", web_path="/y", summary="LVEF 45%"),
    ]
    result = build_knowledge_bus(findings, "P0001", {"name": "Test", "age": 50, "sex": "M", "conditions": []})
    # Should return empty bus on failure, not crash
    for f in findings:
        assert f.agent in result
        assert result[f.agent] == {"supported_by": [], "contradicted_by": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_knowledge_bus.py -v`
Expected: FAIL

- [ ] **Step 3: Implement knowledge_bus.py**

```python
# src/agents/knowledge_bus.py
import json
from google.genai import types
from src.agents.base_agent import Finding
from src.agents.prompts import KNOWLEDGE_BUS_PROMPT_TEMPLATE
from src.core.gemini_client import create_client

GEMINI_MODEL = "gemini-3.1-pro"


def _build_knowledge_bus_prompt(findings: list[Finding], patient_id: str, patient_info: dict) -> str:
    numbered = "\n".join(
        f"{i+1}. {f.agent}: {f.summary}" for i, f in enumerate(findings)
    )
    return KNOWLEDGE_BUS_PROMPT_TEMPLATE.format(
        patient_name=patient_info.get("name", patient_id),
        patient_id=patient_id,
        age=patient_info.get("age", "?"),
        sex=patient_info.get("sex", "?"),
        conditions=", ".join(patient_info.get("conditions", [])) or "None",
        numbered_findings_list=numbered,
    )


def _empty_bus(findings: list[Finding]) -> dict:
    return {f.agent: {"supported_by": [], "contradicted_by": []} for f in findings}


def build_knowledge_bus(findings: list[Finding], patient_id: str, patient_info: dict) -> dict:
    prompt = _build_knowledge_bus_prompt(findings, patient_id, patient_info)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )

    try:
        client = create_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=config,
        )
        bus_data = json.loads(response.text)
    except Exception:
        return _empty_bus(findings)

    # Ensure every finding has an entry
    result = _empty_bus(findings)
    for f in findings:
        if f.agent in bus_data and isinstance(bus_data[f.agent], dict):
            result[f.agent] = {
                "supported_by": bus_data[f.agent].get("supported_by", []),
                "contradicted_by": bus_data[f.agent].get("contradicted_by", []),
            }

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/agents/test_knowledge_bus.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/knowledge_bus.py tests/agents/test_knowledge_bus.py
git commit -m "feat: add knowledge bus for cross-referencing findings"
```

---

## Chunk 5: Orchestrator and Response Assembly

### Task 8: Implement response assembly

**Files:**
- Create: `src/core/response_assembly.py`
- Create: `tests/core/test_response_assembly.py`

- [ ] **Step 1: Write test for assemble_response**

```python
# tests/core/test_response_assembly.py
import json
from src.agents.base_agent import Finding
from src.core.response_assembly import assemble_response

def test_assemble_single_citation():
    findings = [Finding(agent="ecg", file="P0001.svg", web_path="/multimodal-data/ecg/P0001.svg",
                        summary="Normal sinus rhythm")]
    knowledge_bus = {}
    result = json.loads(assemble_response("The ECG [cite:1] is normal.", findings, knowledge_bus))
    assert result["response"] == "The ECG [cite:1] is normal."
    assert len(result["citations"]) == 1
    c = result["citations"][0]
    assert c["id"] == "1"
    assert c["agent"] == "ecg"
    assert c["file"] == "P0001.svg"
    assert c["web_path"] == "/multimodal-data/ecg/P0001.svg"
    assert c["summary"] == "Normal sinus rhythm"
    assert c["knowledge_bus"] == {"supported_by": [], "contradicted_by": []}

def test_assemble_multiple_citations_with_knowledge_bus():
    findings = [
        Finding(agent="ecg", file="P0001.svg", web_path="/ecg", summary="ST depression"),
        Finding(agent="echo", file="P0001.mp4", web_path="/echo", summary="LVEF 45%"),
    ]
    knowledge_bus = {
        "ecg": {"supported_by": [{"agent": "echo", "finding": "LVEF 45%", "reason": "consistent"}], "contradicted_by": []},
        "echo": {"supported_by": [], "contradicted_by": []},
    }
    result = json.loads(assemble_response("ECG [cite:1] and echo [cite:2].", findings, knowledge_bus))
    assert len(result["citations"]) == 2
    assert result["citations"][0]["id"] == "1"
    assert result["citations"][1]["id"] == "2"
    assert len(result["citations"][0]["knowledge_bus"]["supported_by"]) == 1

def test_assemble_returns_valid_json():
    findings = [Finding(agent="ecg", file="P.svg", web_path="/x", summary='Has "quotes" and \\slashes')]
    result = assemble_response("Text", findings, {})
    parsed = json.loads(result)  # should not raise
    assert parsed["citations"][0]["summary"] == 'Has "quotes" and \\slashes'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/core/test_response_assembly.py -v`
Expected: FAIL

- [ ] **Step 3: Implement response_assembly.py**

```python
# src/core/response_assembly.py
import json
from src.agents.base_agent import Finding


def assemble_response(gemini_text: str, findings: list[Finding], knowledge_bus: dict) -> str:
    citations = []
    for i, finding in enumerate(findings):
        citations.append({
            "id": str(i + 1),
            "agent": finding.agent,
            "file": finding.file,
            "web_path": finding.web_path,
            "summary": finding.summary,
            "knowledge_bus": knowledge_bus.get(finding.agent, {
                "supported_by": [],
                "contradicted_by": [],
            }),
        })
    return json.dumps({"response": gemini_text, "citations": citations}, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/core/test_response_assembly.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/response_assembly.py tests/core/test_response_assembly.py
git commit -m "feat: add deterministic response assembly for citations"
```

---

### Task 9: Rewrite orchestrator

**Files:**
- Rewrite: `src/core/orchestrator.py`
- Create: `tests/core/test_orchestrator.py`

- [ ] **Step 1: Write test for orchestrator**

```python
# tests/core/test_orchestrator.py
import json
from unittest.mock import patch, MagicMock
from src.core.orchestrator import run_pipeline, AGENT_REGISTRY, has_function_calls

def test_agent_registry_has_all_seven():
    expected = [
        "analyze_clinical_notes", "analyze_chest_xray", "analyze_ecg",
        "analyze_echo", "analyze_heart_sounds", "analyze_lab_results",
        "analyze_medication",
    ]
    for name in expected:
        assert name in AGENT_REGISTRY

def test_has_function_calls_true():
    mock_response = MagicMock()
    mock_fc = MagicMock()
    mock_fc.function_call = MagicMock()
    mock_fc.function_call.name = "analyze_ecg"
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[-1].content.parts = [mock_fc]
    assert has_function_calls(mock_response) is True

def test_has_function_calls_false_on_text():
    mock_response = MagicMock()
    mock_part = MagicMock()
    mock_part.function_call = None
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[-1].content.parts = [mock_part]
    assert has_function_calls(mock_response) is False

@patch("src.core.orchestrator.build_knowledge_bus")
@patch("src.core.orchestrator.create_client")
def test_pipeline_plain_text_without_tools(mock_create_client, mock_kb):
    """When Gemini doesn't call any tools, return plain text."""
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client

    # Gemini returns text directly (no function calls)
    mock_part = MagicMock()
    mock_part.function_call = None
    mock_part.text = "Atrial fibrillation is a cardiac arrhythmia."
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[-1].content.parts = [mock_part]
    mock_client.models.generate_content.return_value = mock_response

    result = run_pipeline("What is atrial fibrillation?")
    assert result == "Atrial fibrillation is a cardiac arrhythmia."
    mock_kb.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/core/test_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Rewrite orchestrator.py**

```python
# src/core/orchestrator.py
"""
Main orchestrator for the multimodal medical agent system.
Coordinates between specialized agents using Gemini's function calling.
"""
from google.genai import types

from src.tools.definitions import tools
from src.utils.logging import log_user, log_assistant, log_tool_call, log_tool_result
from src.agents.prompts import build_system_prompt
from src.agents.knowledge_bus import build_knowledge_bus
# create_config already exists in gemini_client.py:
# def create_config(tools, system_instruction):
#     return types.GenerateContentConfig(tools=[tools], system_instruction=system_instruction)
from src.core.gemini_client import create_client, create_config
from src.core.response_assembly import assemble_response
from src.agents.base_agent import Finding

from src.agents.clinical_notes_agent import ClinicalNotesAgent
from src.agents.chest_xray_agent import ChestXrayAgent
from src.agents.ecg_agent import EcgAgent
from src.agents.echo_agent import EchoAgent
from src.agents.heart_sounds_agent import HeartSoundsAgent
from src.agents.lab_results_agent import LabResultsAgent
from src.agents.medication_agent import MedicationAgent

GEMINI_MODEL = "gemini-3.1-pro"

AGENT_REGISTRY = {
    "analyze_clinical_notes": ClinicalNotesAgent(),
    "analyze_chest_xray": ChestXrayAgent(),
    "analyze_ecg": EcgAgent(),
    "analyze_echo": EchoAgent(),
    "analyze_heart_sounds": HeartSoundsAgent(),
    "analyze_lab_results": LabResultsAgent(),
    "analyze_medication": MedicationAgent(),
}


def has_function_calls(response) -> bool:
    try:
        parts = response.candidates[-1].content.parts
        return any(p.function_call and p.function_call.name for p in parts)
    except (IndexError, AttributeError):
        return False


def run_pipeline(
    user_query: str,
    conversation_history: list = None,
    patient_id: str = None,
    patient_info: dict = None,
):
    client = create_client()
    system_prompt = build_system_prompt(patient_id, patient_info)
    config = create_config(tools, system_prompt)

    # Build conversation contents
    contents = []
    if conversation_history:
        for msg in conversation_history[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=msg["content"])],
            ))

    contents.append(types.Content(
        role="user", parts=[types.Part(text=user_query)],
    ))
    log_user(user_query)

    # Initial Gemini call
    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=contents, config=config,
    )

    findings: list[Finding] = []

    # Tool loop — handles parallel and sequential calls
    while has_function_calls(response):
        tool_calls = [
            part.function_call
            for part in response.candidates[-1].content.parts
            if part.function_call and part.function_call.name
        ]

        function_responses = []
        for tc in tool_calls:
            agent = AGENT_REGISTRY.get(tc.name)
            if not agent:
                log_tool_call(tc.name, "Unknown tool")
                function_responses.append(
                    types.Part.from_function_response(
                        name=tc.name, response={"error": f"Unknown tool: {tc.name}"},
                    )
                )
                continue

            pid = tc.args.get("patient_id", patient_id)
            query = tc.args.get("query", user_query)
            log_tool_call(tc.name, f"{pid}: {query}")

            finding = agent.analyze(pid, query)
            findings.append(finding)
            log_tool_result(finding.summary)

            function_responses.append(
                types.Part.from_function_response(
                    name=tc.name, response={"summary": finding.summary},
                )
            )

        contents.append(response.candidates[-1].content)
        contents.append(types.Content(role="user", parts=function_responses))

        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=contents, config=config,
        )

    # Extract final text
    gemini_text = response.candidates[-1].content.parts[-1].text
    log_assistant(gemini_text)

    # If no tools were called, return plain text
    if not findings:
        return gemini_text

    # Knowledge bus cross-referencing
    knowledge_bus = {}
    if len(findings) >= 2 and patient_id and patient_info:
        knowledge_bus = build_knowledge_bus(findings, patient_id, patient_info)

    return assemble_response(gemini_text, findings, knowledge_bus)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/core/test_orchestrator.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/orchestrator.py tests/core/test_orchestrator.py
git commit -m "feat: rewrite orchestrator with parallel tool calls and citation assembly"
```

---

## Chunk 6: Cleanup, Logging, and Integration

### Task 10: Update logging and gemini_client

**Files:**
- Modify: `src/utils/logging.py`
- Modify: `src/core/gemini_client.py`

- [ ] **Step 1: Update header_map in logging.py**

In `src/utils/logging.py`, replace the existing `header_map` dict in `log_tool_call()` with:

```python
header_map = {
    "analyze_clinical_notes": "Clinical Notes Analysis",
    "analyze_chest_xray": "Chest X-Ray Analysis",
    "analyze_ecg": "ECG Analysis",
    "analyze_echo": "Echocardiogram Analysis",
    "analyze_heart_sounds": "Heart Sounds Analysis",
    "analyze_lab_results": "Lab Results Analysis",
    "analyze_medication": "Medication Analysis",
}
```

- [ ] **Step 2: Remove dead code from logging.py**

Remove these functions from `src/utils/logging.py`:
- `write_agent_summary()`
- `read_agent_summary()`
- `read_all_summaries()`

Also remove the `xml.etree.ElementTree`, `xml.dom.minidom` imports if no longer used.

- [ ] **Step 3: Verify gemini_client.py**

The model string is not hardcoded in `gemini_client.py` — callers pass the model. No changes needed. Verify with:

Run: `cd /Users/maksym/personal/MedDataOS && grep -n "gemini" src/core/gemini_client.py`
Expected: No model name strings found (only variable references)

- [ ] **Step 4: Delete shared_knowledge.xml if it exists**

```bash
rm -f shared_knowledge.xml
```

- [ ] **Step 5: Commit**

```bash
git add src/utils/logging.py
git rm -f shared_knowledge.xml 2>/dev/null; true
git commit -m "refactor: update logging header_map for new agents, remove dead XML code"
```

---

### Task 11: Delete old files and update server.py

**Files:**
- Delete: `src/agents/executors.py`
- Modify: `web/backend/server.py` (remove `uploaded_file` parameter from `run_pipeline` call)

- [ ] **Step 1: Delete executors.py**

```bash
git rm src/agents/executors.py
```

- [ ] **Step 2: Update server.py run_pipeline call**

The server calls `run_pipeline()` in `web/backend/server.py`. Update the call to match the new signature (no `uploaded_file` parameter). Find the line that calls `run_pipeline` and update it:

```python
# Old:
result = run_pipeline(message, session["history"], uploaded_file=session.get("uploaded_file"),
                      patient_id=patient_id, patient_info=patient_info)
# New:
result = run_pipeline(message, session["history"],
                      patient_id=patient_id, patient_info=patient_info)
```

Also remove the old imports at the top of `server.py` if they reference `INITIAL_QUERY` or agents from `executors.py`. Read `web/backend/server.py` to find the exact line that calls `run_pipeline` and adapt accordingly.

- [ ] **Step 3: Run all tests**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add web/backend/server.py
git commit -m "refactor: remove executors.py, update server.py for new pipeline"
```

---

### Task 12: End-to-end smoke test

**Files:**
- Create: `tests/test_e2e_smoke.py`

- [ ] **Step 1: Write end-to-end test**

```python
# tests/test_e2e_smoke.py
"""
Smoke test: verifies the full pipeline can assemble a valid citation response
from stub agents without actually calling Gemini.
"""
import json
from unittest.mock import patch, MagicMock
from src.core.orchestrator import run_pipeline

@patch("src.core.orchestrator.create_client")
def test_e2e_single_modality(mock_orch_client):
    """Simulate Gemini calling analyze_ecg and composing a response.
    Knowledge bus is NOT called (single modality), so no need to mock it."""
    mock_client = MagicMock()
    mock_orch_client.return_value = mock_client

    # First call: Gemini returns a function call
    fc_part = MagicMock()
    fc_part.function_call = MagicMock()
    fc_part.function_call.name = "analyze_ecg"
    fc_part.function_call.args = {"patient_id": "P0001", "query": "cardiac workup"}
    response1 = MagicMock()
    response1.candidates = [MagicMock()]
    response1.candidates[-1].content.parts = [fc_part]

    # Second call: Gemini returns text with citation
    text_part = MagicMock()
    text_part.function_call = None
    text_part.text = "The ECG [cite:1] shows normal sinus rhythm."
    response2 = MagicMock()
    response2.candidates = [MagicMock()]
    response2.candidates[-1].content.parts = [text_part]

    mock_client.models.generate_content.side_effect = [response1, response2]

    patient_info = {"name": "James Carter", "age": 58, "sex": "M",
                    "blood_type": "A+", "allergies": ["Penicillin"],
                    "conditions": ["HTN"], "data_dates": {"ecg": "2026-02-03"}}

    result = run_pipeline("What does the ECG show?", patient_id="P0001", patient_info=patient_info)
    parsed = json.loads(result)

    assert "response" in parsed
    assert "[cite:1]" in parsed["response"]
    assert len(parsed["citations"]) == 1
    assert parsed["citations"][0]["agent"] == "ecg"
    assert parsed["citations"][0]["id"] == "1"
    assert "P0001.svg" in parsed["citations"][0]["file"]
```

- [ ] **Step 2: Run the test**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/test_e2e_smoke.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_smoke.py
git commit -m "test: add end-to-end smoke test for citation pipeline"
```

---

### Task 13: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `cd /Users/maksym/personal/MedDataOS && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify server starts**

Run: `cd /Users/maksym/personal/MedDataOS && timeout 5 python web/backend/server.py || true`
Expected: Server starts without import errors (will timeout after 5s — that's fine)

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git status
# If clean, nothing to commit. If changes exist, stage specific files:
# git add <specific files>
# git commit -m "chore: final cleanup"
```
