# Decouple Citation Review State from Pin System

**Date:** 2026-03-18
**Status:** Draft

## Problem

Citation review state (checkboxes that control badge colors: red/yellow/green) is currently stored on pin objects (`pin.checklist_state`). This creates tight coupling:

- Checkbox persistence requires a pin to exist
- Checking a checkbox triggers pin panel re-renders
- `ensurePinned()` auto-pins citations when annotations are added
- Dual state sources (`citation.review` vs `pin.checklist_state`) create confusion about source of truth
- Badge color computation (`updateCitationBadgeStates()`) must scan all pins to build a progress map

## Goal

Separate two independent concerns:

- **Pins** = pinning citations to the side panel for organization (with annotations/tags)
- **Review checkboxes** = tracking which findings have been reviewed (controls badge color only)

These should not interact. Checking a checkbox should not affect the pin panel. Pinning should not affect badge colors.

## Design

### Backend

#### New Storage

```python
# server.py - module level
patient_reviews = {}  # {patient_id: {"agent|web_path": {"0": True, "1": False, ...}}}
```

#### New Endpoints

**GET `/api/patients/{patient_id}/reviews`**
- Returns: `patient_reviews.get(patient_id, {})`

**PATCH `/api/patients/{patient_id}/reviews`**
- Body: `{"key": "ecg|/multimodal-data/ecg/P0001.svg", "checklist_state": {"0": true, "1": false}}`
- Upserts the entry in `patient_reviews[patient_id][key]`
- Returns 422 if `key` is missing/empty
- Permissive on `checklist_state` shape (stores whatever is sent, no validation against summary item count)
- To reset: send `checklist_state: {}` — treated as 0 items checked (red badge)
- Returns: updated entry

#### Pin Endpoint Changes

- `POST /api/patients/{patient_id}/pins`: Remove `checklist_state` from new pin initialization entirely (not `{}`, just omit the field)
- `PATCH /api/patients/{patient_id}/pins/{pin_id}`: Remove `checklist_state` handling (only `annotations` remain)
- Strip `checklist_state` from all pin API responses to enforce clean separation

#### Demo Data Migration

Move **all** preset review states to `patient_reviews[X]`. This includes:

1. Review states from `patient_pins[X][].checklist_state` (3 pins per patient)
2. Review states from `citation.review` fields on citation objects embedded in demo session messages (via `_cite()` helper's `review` parameter)

Both sources must be migrated so that citations currently showing green/yellow badges via the `citation.review` fallback don't regress to red.

Example:
```python
patient_reviews["P0001"] = {
    "ecg|/multimodal-data/ecg/P0001.svg": {"0": True, "1": True, "2": True, "3": True},
    "lab_results|/multimodal-data/lab-results/P0001.png": {"0": True, "1": True, "2": False, "3": False},
    "medication|/multimodal-data/medications/P0001.csv": {"0": True, "1": True, "2": True, "3": True},
    # ... all citations that had review= set in their _cite() calls
}
```

Demo pins lose their `checklist_state` field entirely. The `citation.review` field on citation objects can remain in the JSON (embedded in session messages, not trivially removable), but is no longer read by frontend code.

### Frontend

#### New State

```javascript
const patientReviews = {};  // {patientId: {"agent|web_path": {checklist_state}}}
```

#### New Functions

```javascript
async function fetchReviews(patientId) {
    const res = await fetch(`/api/patients/${patientId}/reviews`);
    patientReviews[patientId] = await res.json();
}

async function patchReview(patientId, key, checklist_state) {
    await fetch(`/api/patients/${patientId}/reviews`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key, checklist_state}),
    });
    patientReviews[patientId] = patientReviews[patientId] || {};
    patientReviews[patientId][key] = checklist_state;
}

const debouncedPatchReview = debounce((patientId, key, state) => {
    patchReview(patientId, key, state);
}, 500);
```

#### Modified Functions

**`switchConversation()`**: Fetch reviews alongside pins on patient switch.

**`openCitationModal()`**: Read checklist state from `patientReviews[activePatientId]["agent|web_path"]` instead of from pin or `citation.review`.

**Checkbox change handler**:
- Remove the `if (!activePatientId || !currentModalPin) return;` guard — checkbox persistence no longer requires a pin
- Remove any call to `ensurePinned()` from the checkbox path
- Call `debouncedPatchReview()` instead of `debouncedPatchChecklist()`. Only call `updateCitationBadgeStates()` — do NOT call `renderInsightsPanel()`.

**`updateCitationBadgeStates()`**: Read from `patientReviews[activePatientId]` directly by `agent|web_path` key. No need to scan pins or build `progressMap`. **Remove the `citation.review` fallback** (currently at ~lines 305-306) — `patientReviews` is the sole source of truth.

**`renderInsightsPanel()`**: Remove progress bar from pinned cards. Pins show: agent label, preview, summary, annotations, tags, unpin button. No review progress.

#### Removed

- `getPinProgress()` — no longer needed
- `debouncedPatchChecklist()` — replaced by `debouncedPatchReview()`
- `checklist_state` handling in `patchPin()` — only annotations remain

#### Unchanged

- Pin creation/deletion (📌 button workflow)
- `ensurePinned()` — still used for annotation/tag persistence only (no longer called from checkbox path)
- `parseSummaryToChecklist()` — still parses summary into checkbox items
- Badge color CSS classes (`citation-review-none`, `citation-review-partial`, `citation-review-complete`)
- Conflict indicators (`citation-has-conflict`)
- `findPinId()` — still used for pin deduplication

## Data Flow (After)

```
Checkbox change → debouncedPatchReview() → PATCH /reviews → updateCitationBadgeStates()
                                                            (badge colors only, no pin panel touch)

Pin button → addPin()/removePin() → POST/DELETE /pins → renderInsightsPanel()
                                                        (pin panel only, no badge color touch)
```

## Migration Notes

- No database migration needed (in-memory storage)
- Demo data restructured in `_seed_demo_sessions()`
- `citation.review` fields remain embedded in demo session message JSON (not trivially removable without re-serializing all messages) but are **never read** by frontend after the refactor
- `updateCitationBadgeStates()` must not fall back to `citation.review` — only `patientReviews`
- Live pipeline does not set review state; new citations start with no review (red badge)

## Known Limitations

- Single-user app — no cache invalidation across browser tabs. Same issue exists with pins today.
