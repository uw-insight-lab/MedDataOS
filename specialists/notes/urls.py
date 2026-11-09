"""Path of the MedDataOS route that serves a highlighted note span."""

from __future__ import annotations

from urllib.parse import quote


def note_span_url(patient_id: str, doc_id: str, start: int, end: int) -> str:
    """URL for a highlighted note span (native note or OCR transcript)."""
    return (
        f"/api/cases/{quote(patient_id, safe='')}/notes/span"
        f"?id={quote(doc_id, safe='')}&start={int(start)}&end={int(end)}"
    )
