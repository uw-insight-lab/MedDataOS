"""One imaging read: choose a series, render one slice, describe that slice."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

from meddataos.datactrl.errors import DataCtrlError

from meddataos.specialists.azure import azure_chat, azure_configured
from meddataos.specialists.gemini import GEMINI_MODEL, create_client
from meddataos.specialists.imaging.select import (
    choose_preview_window,
    parse_query_intent,
    rank_series,
)

_ANALYSIS_PROMPT = """You are a radiology specialist looking at a single DICOM slice preview (not a full study read).

Question: {query}

Series: {label} ({modality})
Resource id: {resource_id}
Kind: {series_kind}
Slice {slice_index} of {n_slices}
Window: {window}
{overlay_block}
{warnings}

Answer in two to four plain sentences of prose. No markdown, no headings, no bullet points, no image links, and do not repeat the series name, slice number, window, or resource id; they are attached separately.

Describe only anatomy that is visible on this slice. If contours are overlaid, name structures from the ROI list and the drawn outlines. Do not invent extra ROIs. If the series is a runoff/extremity protocol, do not assume a dedicated liver/abdomen acquisition. Do not invent organs that are not in the frame. Be explicit that this is one preview slice, not a complete interpretation."""

# Contour objects are previewed on the image series they reference, and
# datactrl centres the slice on the structure unless an index is given.
_CONTOUR_KINDS = frozenset({"rtstruct", "seg"})


@dataclass
class SliceRead:
    """One imaging read. A series path means the file can be cited."""

    summary: str
    file: str
    series_id: str = ""
    series_path: str = ""
    preview: dict | None = None


def read_slice(
    case,
    query: str,
    resource_id: str | None = None,
    slice_index: int | None = None,
) -> SliceRead:
    """Rank series, render one preview, and describe that slice.

    No confident series means the ranked list and no image.
    """
    refs = list(case.report.dicom)
    if not refs:
        return SliceRead(summary="No DICOM series in this case.", file="imaging.txt")

    ranked = rank_series(refs, query, limit=5)
    chosen = _resolve_series(refs, ranked, resource_id)
    if chosen is None:
        return SliceRead(summary=_format_candidates(ranked), file="dicom_select.txt")

    series_id = chosen["id"]
    ref = next(item for item in refs if item.id == series_id)
    label = ref.label or series_id
    modality = ref.meta.get("Modality") or "DICOM"
    series_kind = str(ref.meta.get("series_kind") or "acquisition")
    is_contour = series_kind in _CONTOUR_KINDS
    if slice_index is None and not is_contour:
        slice_index = chosen.get("suggested_slice_index")
    warnings = list(chosen.get("warnings") or [])
    intent = parse_query_intent(query)
    pixel_modality = "CT" if is_contour else str(modality)
    window = choose_preview_window(pixel_modality, intent)
    series_path = str(ref.path or "")

    fetch_opts: dict = {"window": window}
    if slice_index is not None:
        fetch_opts["slice_index"] = int(slice_index)
    if is_contour or intent.contours:
        fetch_opts["overlay"] = True
    try:
        preview = case.fetch(series_id, view="preview", **fetch_opts)
    except (DataCtrlError, ValueError) as exc:
        return SliceRead(
            summary=f"Could not render a preview for series {label}: {exc}",
            file=f"{label}.png",
            series_id=series_id,
            series_path=series_path,
        )
    data = preview.get("data") or {}
    encoded = data.get("image_base64")
    if not encoded:
        return SliceRead(
            summary=f"Could not render a preview for series {label}.",
            file=f"{label}.png",
            series_id=series_id,
            series_path=series_path,
        )

    meta = data.get("meta") or {}
    png = base64.b64decode(encoded)
    summary = _describe_slice(
        png,
        _ANALYSIS_PROMPT.format(
            query=query,
            label=label,
            modality=modality,
            resource_id=series_id,
            series_kind=series_kind,
            slice_index=meta.get("slice_index", "?"),
            n_slices=meta.get("n_slices", "?"),
            window=meta.get("window", window),
            overlay_block=_overlay_prompt_block(ref.meta, meta),
            warnings=("Warnings: " + "; ".join(warnings)) if warnings else "",
        ),
    )
    shown = meta.get("slice_index", slice_index)
    try:
        shown_index = int(shown)
    except (TypeError, ValueError):
        shown_index = None
    return SliceRead(
        summary=summary,
        file=f"{label}.png",
        series_id=series_id,
        series_path=series_path,
        preview={
            "slice_index": shown_index,
            "window": str(meta.get("window") or window),
            "overlay": bool(meta.get("overlay", fetch_opts.get("overlay"))),
        },
    )


def _describe_slice(png: bytes, prompt: str) -> str:
    """Describe one slice with the Azure deployment when set, otherwise Gemini."""
    if azure_configured():
        image = "data:image/png;base64," + base64.b64encode(png).decode()
        message = azure_chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image}},
                    ],
                }
            ]
        )
        return _plain(message.get("content")) or "Preview retrieved but no interpretation was produced."

    from google.genai import types

    response = create_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=png, mime_type="image/png"),
                    types.Part.from_text(text=prompt),
                ],
            )
        ],
    )
    return _plain(response.text) or "Preview retrieved but no interpretation was produced."


_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_ATTACHED_LINE = re.compile(r"^\W*(?:series|slice|window|citation|resource id)\s*:.*$", re.I | re.M)


def _plain(text: str | None) -> str:
    """The model's description without image links or lines that repeat attached facts."""
    cleaned = _IMAGE_LINK.sub("", text or "")
    cleaned = _ATTACHED_LINE.sub("", cleaned)
    return cleaned.replace("**", "").strip()


def _overlay_prompt_block(ref_meta: dict, fetch_meta: dict) -> str:
    """ROI names from the structure set plus what was drawn on this slice."""
    names = list(ref_meta.get("roi_names") or fetch_meta.get("roi_names") or [])
    drawn = list(fetch_meta.get("overlay_rois") or [])
    if not names and not drawn:
        return ""
    lines = []
    if names:
        lines.append("Structure-set ROI names: " + ", ".join(str(n) for n in names))
    if drawn:
        parts = [
            f"{item.get('name')} ({item.get('color')})"
            if item.get("color")
            else str(item.get("name"))
            for item in drawn
        ]
        lines.append("Contours drawn on this slice: " + ", ".join(parts))
    elif fetch_meta.get("overlay") is False:
        lines.append("No contours fell on this slice.")
    return "\n".join(lines)


def _resolve_series(refs: list, ranked: dict, resource_id: str | None) -> dict | None:
    """Honor an explicit resource_id; otherwise require a confident ranker pick."""
    if resource_id:
        ref = next((item for item in refs if item.id == resource_id), None)
        if ref is None:
            return None
        one = rank_series([ref], ranked.get("query") or "", limit=1, include_localizers=True)
        if one["candidates"]:
            return one["candidates"][0]
        return {
            "id": ref.id,
            "label": ref.label,
            "suggested_slice_index": ref.meta.get("suggested_slice_index"),
            "warnings": [],
        }
    if ranked.get("confident") and ranked.get("selected"):
        return ranked["selected"]
    return None


def _format_candidates(ranked: dict) -> str:
    """Fail closed: return ranked options instead of guessing a series."""
    intent = ranked.get("intent") or {}
    lines = [
        "No confident DICOM series match. Ranked candidates "
        "(name one by its resource id to read it):",
        f"intent={intent}",
    ]
    for item in ranked.get("candidates") or []:
        reasons = ", ".join(item.get("reasons") or [])
        lines.append(
            f"- {item.get('id')}: {item.get('label')} "
            f"({item.get('Modality')}, {item.get('series_kind')}, "
            f"n={item.get('instance_count')}, slice={item.get('suggested_slice_index')}) "
            f"score={item.get('score')} {reasons}"
        )
    if len(lines) == 2:
        lines.append("- (none)")
    return "\n".join(lines)
