# Decouple Review State from Pins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate citation review state (checkboxes/badge colors) from the pin system so they are fully independent concerns.

**Architecture:** New `patient_reviews` dict on backend keyed by `patient_id → "agent|web_path" → checklist_state`. New GET/PATCH endpoints. Frontend reads review state from dedicated `patientReviews` cache instead of from pins. Progress bars removed from pin cards.

**Tech Stack:** Python/FastAPI (backend), vanilla JS (frontend)

**Spec:** `docs/superpowers/specs/2026-03-18-decouple-review-from-pins-design.md`

> **Note:** Line numbers reference the original unmodified files. After earlier tasks shift content, use the provided code snippets to locate targets.

---

### Task 1: Add `patient_reviews` storage and endpoints to backend

**Files:**
- Modify: `web/backend/server.py:43` (add new dict)
- Modify: `web/backend/server.py` (add two new endpoints between line 1197 and the health check endpoint at line 1200)

- [ ] **Step 1: Add `patient_reviews` dict at module level**

After line 43 (`patient_pins = {}`), add:

```python
patient_reviews = {}   # {patient_id: {"agent|web_path": {"0": True, ...}}}
```

- [ ] **Step 2: Add GET endpoint**

Add between line 1197 (end of PATCH /pins) and line 1200 (health check endpoint):

```python
@app.get("/api/patients/{patient_id}/reviews")
async def get_patient_reviews(patient_id: str):
    """Return review checklist states for a patient."""
    return patient_reviews.get(patient_id, {})
```

- [ ] **Step 3: Add PATCH endpoint**

```python
@app.patch("/api/patients/{patient_id}/reviews")
async def patch_patient_review(patient_id: str, request: dict):
    """Upsert review checklist state for a citation."""
    key = request.get("key", "").strip()
    if not key:
        return JSONResponse(status_code=422, content={"error": "key is required"})
    checklist_state = request.get("checklist_state", {})
    patient_reviews.setdefault(patient_id, {})[key] = checklist_state
    return {"key": key, "checklist_state": checklist_state}
```

- [ ] **Step 4: Verify server starts**

Run: `cd /Users/maksym/personal/MedDataOS && python -c "import web.backend.server"`
Expected: No import errors

- [ ] **Step 5: Commit**

```bash
git add web/backend/server.py
git commit -m "Add patient_reviews storage and GET/PATCH endpoints"
```

---

### Task 2: Migrate demo data from pins to `patient_reviews`

**Files:**
- Modify: `web/backend/server.py:520-564` (demo pins — remove checklist_state)
- Modify: `web/backend/server.py` (add patient_reviews population in `_seed_demo_sessions()`)

- [ ] **Step 1: Add `patient_reviews` population in `_seed_demo_sessions()`**

Insert immediately after the `patient_pins["P0003"]` closing bracket (line 564), before the `sessions["demo-5"]` block (line 566). Build reviews from ALL citation builders that have `review=` set:

```python
    # ── Demo review states (decoupled from pins) ────────────────
    # P0001: all 7 citations have review presets
    patient_reviews["P0001"] = {
        f"{c['agent']}|{c['web_path']}": c["review"]
        for c in [_c_notes(0), _c_xray(0), _c_ecg(0), _c_heart(0), _c_echo(0), _c_labs(0), _c_meds(0)]
        if c.get("review")
    }
    # P0002
    patient_reviews["P0002"] = {
        f"{c['agent']}|{c['web_path']}": c["review"]
        for c in [_c2_notes(0), _c2_xray(0), _c2_ecg(0), _c2_heart(0), _c2_echo(0), _c2_labs(0), _c2_meds(0)]
        if c.get("review")
    }
    # P0003
    patient_reviews["P0003"] = {
        f"{c['agent']}|{c['web_path']}": c["review"]
        for c in [_c3_notes(0), _c3_xray(0), _c3_ecg(0), _c3_heart(0), _c3_echo(0), _c3_labs(0), _c3_meds(0)]
        if c.get("review")
    }
```

- [ ] **Step 2: Remove `checklist_state` from demo pins**

In `patient_pins["P0001"]` (lines 520-533), `patient_pins["P0002"]` (lines 535-549), `patient_pins["P0003"]` (lines 551-564):

Remove all `"checklist_state": {...}` entries from every pin dict. The pin dicts should end with `"annotations": {"text": "", "tags": []}` and no `checklist_state` key.

- [ ] **Step 3: Verify server starts**

Run: `cd /Users/maksym/personal/MedDataOS && python -c "import web.backend.server"`
Expected: No import errors

- [ ] **Step 4: Commit**

```bash
git add web/backend/server.py
git commit -m "Migrate demo review state from pins to patient_reviews"
```

---

### Task 3: Remove `checklist_state` from pin endpoints

**Files:**
- Modify: `web/backend/server.py:1150-1156` (POST /pins — remove checklist_state init)
- Modify: `web/backend/server.py:1186-1197` (PATCH /pins — remove checklist_state handling)

- [ ] **Step 1: Remove `checklist_state` from POST /pins**

In the POST endpoint (line 1151-1156), remove `"checklist_state": {}` from the `pins.append(...)` dict. The new pin dict should be:

```python
pins.append({"pin_id": pin_id, "type": "citation", "citation": citation,
              "source": request.get("source", ""),
              "created_at": datetime.now(timezone.utc).isoformat(),
              "query": request.get("query", ""),
              "annotations": {"text": "", "tags": []}})
```

- [ ] **Step 2: Remove `checklist_state` from PATCH /pins**

In the PATCH endpoint (lines 1186-1197), remove the `checklist_state` handling. Update docstring:

```python
@app.patch("/api/patients/{patient_id}/pins/{pin_id}")
async def patch_patient_pin(patient_id: str, pin_id: str, request: dict):
    """Update annotations for a pin."""
    pins = patient_pins.get(patient_id, [])
    for p in pins:
        if p["pin_id"] == pin_id:
            if "annotations" in request:
                p["annotations"] = request["annotations"]
            return p
    return {"status": "error", "message": "Pin not found"}
```

- [ ] **Step 3: Verify server starts**

Run: `cd /Users/maksym/personal/MedDataOS && python -c "import web.backend.server"`

- [ ] **Step 4: Commit**

```bash
git add web/backend/server.py
git commit -m "Remove checklist_state from pin endpoints"
```

---

### Task 4: Add `patientReviews` state and fetch/patch functions to frontend

**Files:**
- Modify: `web/frontend/app.js:17` (add new state variable)
- Modify: `web/frontend/app.js:205-213` (add fetchReviews near fetchPins)
- Modify: `web/frontend/app.js:1236-1293` (add patchReview, debouncedPatchReview)

- [ ] **Step 1: Add state variable**

After line 17 (`let patientPins = {};`), add:

```javascript
let patientReviews = {};  // patient_id -> {"agent|web_path": {"0": true, ...}}
```

- [ ] **Step 2: Add `fetchReviews()` function**

After `fetchPins()` (after line 213), add:

```javascript
async function fetchReviews(patientId) {
    try {
        const res = await fetch(`/api/patients/${patientId}/reviews`);
        if (res.ok) patientReviews[patientId] = await res.json();
        else patientReviews[patientId] = {};
    } catch (e) {
        console.error('Failed to fetch reviews:', e);
        patientReviews[patientId] = {};
    }
}
```

- [ ] **Step 3: Add `patchReview()` and debounced version**

After the `debounce()` function (~line 1239), add:

```javascript
async function patchReview(patientId, key, checklist_state) {
    try {
        await fetch(`/api/patients/${patientId}/reviews`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, checklist_state }),
        });
        patientReviews[patientId] = patientReviews[patientId] || {};
        patientReviews[patientId][key] = checklist_state;
    } catch (e) {
        console.error('Failed to patch review:', e);
    }
}

const debouncedPatchReview = debounce((patientId, key, state) => {
    patchReview(patientId, key, state);
}, 500);
```

- [ ] **Step 4: Commit**

```bash
git add web/frontend/app.js
git commit -m "Add patientReviews state and fetch/patch functions"
```

---

### Task 5: Rewire `switchConversation()` to fetch reviews

**Files:**
- Modify: `web/frontend/app.js:536-542` (add fetchReviews call)

- [ ] **Step 1: Add `fetchReviews()` alongside `fetchPins()`**

At lines 539-541, change:

```javascript
    if (changingPatient) {
        await fetchPins(patientId);
    }
```

To:

```javascript
    if (changingPatient) {
        await Promise.all([fetchPins(patientId), fetchReviews(patientId)]);
    }
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/app.js
git commit -m "Fetch reviews alongside pins on patient switch"
```

---

### Task 6: Rewire `updateCitationBadgeStates()` to use `patientReviews`

**Files:**
- Modify: `web/frontend/app.js:278-325`

- [ ] **Step 1: Replace the function body**

Replace the entire `updateCitationBadgeStates()` function (lines 278-325) with:

```javascript
function updateCitationBadgeStates() {
    if (!activePatientId) return;
    const reviews = patientReviews[activePatientId] || {};
    chatContainer.querySelectorAll('.citation').forEach(badge => {
        badge.classList.remove('citation-review-none', 'citation-review-partial', 'citation-review-complete', 'citation-has-conflict');
        try {
            const citation = JSON.parse(decodeURIComponent(badge.dataset.citation));
            const key = citation.agent + '|' + citation.web_path;
            const items = parseSummaryToChecklist(citation.summary);
            const total = items ? items.length : 0;
            const state = reviews[key] || {};
            const checked = items ? items.filter((_, i) => state[String(i)]).length : 0;

            if (total > 0) {
                if (checked === 0) {
                    badge.classList.add('citation-review-none');
                } else if (checked >= total) {
                    badge.classList.add('citation-review-complete');
                } else {
                    badge.classList.add('citation-review-partial');
                }
            }
            const conflict = getCitationConflict(citation);
            if (conflict) {
                badge.classList.add('citation-has-conflict');
            }
        } catch (e) { /* skip malformed */ }
    });
}
```

Key changes: no pin scanning, no `progressMap`, no `citation.review` fallback. Reads directly from `patientReviews`.

- [ ] **Step 2: Commit**

```bash
git add web/frontend/app.js
git commit -m "Rewire badge states to read from patientReviews"
```

---

### Task 7: Rewire checkbox handler in `openCitationModal()`

**Files:**
- Modify: `web/frontend/app.js:1579-1605`

- [ ] **Step 1: Change checklist state resolution**

Replace line 1581:
```javascript
        const checklist_state = pin ? (pin.checklist_state || {}) : (citation.review || {});
```

With:
```javascript
        const reviewKey = citation.agent + '|' + citation.web_path;
        const checklist_state = (patientReviews[activePatientId] || {})[reviewKey] || {};
```

- [ ] **Step 2: Rewire checkbox change handler**

Replace lines 1593-1605:
```javascript
        ul.querySelectorAll('input[type="checkbox"]').forEach((cb, i) => {
            cb.addEventListener('change', async () => {
                const li = cb.closest('li');
                li.classList.toggle('checked', cb.checked);
                if (!activePatientId || !currentModalPin) return;
                currentModalPin.checklist_state = currentModalPin.checklist_state || {};
                currentModalPin.checklist_state[String(i)] = cb.checked;
                debouncedPatchChecklist(activePatientId, currentModalPin.pin_id,
                    { ...currentModalPin.checklist_state });
                renderInsightsPanel();
                updateCitationBadgeStates();
            });
        });
```

With:
```javascript
        ul.querySelectorAll('input[type="checkbox"]').forEach((cb, i) => {
            cb.addEventListener('change', async () => {
                const li = cb.closest('li');
                li.classList.toggle('checked', cb.checked);
                if (!activePatientId) return;
                const rKey = citation.agent + '|' + citation.web_path;
                const current = (patientReviews[activePatientId] || {})[rKey] || {};
                current[String(i)] = cb.checked;
                patientReviews[activePatientId] = patientReviews[activePatientId] || {};
                patientReviews[activePatientId][rKey] = current;
                debouncedPatchReview(activePatientId, rKey, { ...current });
                updateCitationBadgeStates();
            });
        });
```

Key changes: no `currentModalPin` guard, no `ensurePinned()`, no `renderInsightsPanel()`, uses `debouncedPatchReview` instead of `debouncedPatchChecklist`.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/app.js
git commit -m "Decouple checkbox handler from pin system"
```

---

### Task 8: Remove progress bar from `renderInsightsPanel()` and clean up dead code

**Files:**
- Modify: `web/frontend/app.js:384-393` (remove progress bar from pin cards)
- Modify: `web/frontend/app.js:267-275` (remove `getPinProgress()`)
- Modify: `web/frontend/app.js:1291-1293` (remove `debouncedPatchChecklist`)
- Modify: `web/frontend/app.js:1268-1285` (remove checklist_state from `patchPin()`)

- [ ] **Step 1: Remove progress bar from `renderInsightsPanel()`**

In `renderInsightsPanel()`, remove lines 384-393 (the `getPinProgress` call and `progressHTML` construction):

```javascript
            const progress = getPinProgress(p);
            let progressHTML = '';
            if (progress) {
                const pct = Math.round((progress.checked / progress.total) * 100);
                const state = progress.checked === 0 ? 'review-none' : progress.complete ? 'review-complete' : 'review-partial';
                progressHTML = `<div class="pinned-card-progress ${state}">
                    <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
                    <span class="progress-label">${progress.checked}/${progress.total}</span>
                </div>`;
            }
```

Also remove `${progressHTML}` from the card innerHTML template (line 404).

- [ ] **Step 2: Remove `getPinProgress()` function**

Delete lines 267-275 entirely.

- [ ] **Step 3: Remove `debouncedPatchChecklist`**

Delete lines 1291-1293:
```javascript
const debouncedPatchChecklist = debounce((patientId, pinId, checklist_state) => {
    patchPin(patientId, pinId, { checklist_state });
}, 500);
```

- [ ] **Step 4: Remove `checklist_state` handling from `patchPin()`**

In `patchPin()` (lines 1268-1285), remove line 1280:
```javascript
            if (data.checklist_state !== undefined) pin.checklist_state = data.checklist_state;
```

- [ ] **Step 5: Commit**

```bash
git add web/frontend/app.js
git commit -m "Remove progress bar from pins, clean up dead review code"
```

---

### Task 9: Manual smoke test

- [ ] **Step 1: Start the server**

Run: `cd /Users/maksym/personal/MedDataOS && python web/backend/server.py`

- [ ] **Step 2: Verify demo badge colors**

Open browser to `http://127.0.0.1:8080`. Select patient P0001, click a demo conversation. Verify citation badges show correct colors (green for fully reviewed, yellow for partial, red for none) — same as before the refactor.

- [ ] **Step 3: Verify checkbox interaction**

Click a citation badge to open the modal. Toggle a checkbox. Close the modal. Verify the badge color updated. Verify the pin panel did NOT re-render or change.

- [ ] **Step 4: Verify pin independence**

Pin an unpinned citation. Verify it appears in the side panel without a progress bar. Toggle checkboxes on it. Verify badge color changes but pin card stays the same.

- [ ] **Step 5: Verify unpinned checkbox persistence**

Open an unpinned citation modal. Toggle a checkbox. Close and reopen. Verify the checkbox state persisted (it should — no pin required now).

- [ ] **Step 6: Commit any fixes if needed**

```bash
git add web/backend/server.py web/frontend/app.js
git commit -m "Fix issues found during smoke test"
```
