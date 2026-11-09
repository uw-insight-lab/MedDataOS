"""Pick a DICOM series for a question, from series tags and geometry only.

datactrl describes every series (`ResourceRef.meta`: modality, descriptions,
kind, slice count, z extent, RTSTRUCT ROI names). This module turns a
free-text question into a ranked list over that metadata. It reads no pixels
and calls no model. A pick is "confident" only when the best series fits the
modality and anatomy asked for; otherwise the caller gets candidates, not a guess.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from meddataos.datactrl.types import ResourceRef
from meddataos.datactrl.utils.dicom_meta import (
    LONG_FOV_MM,
    infer_regions,
    suggested_slice_index,
)

_REGION_PRIORITY = ("abdomen", "chest", "neck", "head", "pelvis", "extremity")
_ORGAN_REGIONS = frozenset({"abdomen", "chest", "neck", "head"})

# Kinds whose preview is drawn on a referenced image series (or has no pixels).
_RT_KINDS = frozenset({"rtstruct", "rtplan", "rtdose"})
_CONTOUR_KINDS = frozenset({"rtstruct", "seg"})

_MODALITY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("CT", r"\b(?:ct|cta|ctp)\b"),
    ("MR", r"\b(?:mr|mri)\b"),
    ("PT", r"\b(?:pt|pet)\b"),
    ("US", r"\b(?:us|ultrasound)\b"),
    ("NM", r"\bnm\b"),
    ("SEG", r"\bseg(?:mentation)?s?\b"),
    ("RTSTRUCT", r"\brt[\s-]?struct\b"),
    ("RTPLAN", r"\brtplan\b"),
    ("RTDOSE", r"\brtdose\b"),
)
_CONTOUR_RE = re.compile(
    r"\b(?:contours?|contoured|rt[\s-]?struct|structure set|segmentations?|"
    r"rois?|gtv\w*|ptv\w*|ctv\w*|overlay|delineat\w*|outlined|"
    r"oars?|organs at risk|target volumes?)\b",
    re.I,
)


@dataclass(frozen=True)
class QueryIntent:
    """Modalities and anatomic regions asked for in a question."""

    modalities: frozenset[str]
    regions: frozenset[str]
    raw: str
    contours: bool = False


def parse_query_intent(query: str) -> QueryIntent:
    """Extract requested modalities, anatomic regions, and contour wording."""
    text = (query or "").lower()
    modalities = {
        modality for modality, pattern in _MODALITY_PATTERNS if re.search(pattern, text)
    }
    return QueryIntent(
        modalities=frozenset(modalities),
        regions=infer_regions(text),
        raw=query or "",
        contours=bool(_CONTOUR_RE.search(text)),
    )


def choose_preview_window(modality: str | None, intent: QueryIntent | None) -> str:
    """Display window for a query: CT window by anatomy, PET percentile, else min-max."""
    kind = str(modality or "").upper()
    if kind == "PT":
        return "pet"
    if kind != "CT":
        return "minmax"
    region = _primary_region(intent)
    if region == "abdomen":
        return "liver"
    if region == "chest":
        return "lung"
    if region == "head":
        return "brain"
    return "abdomen"


def rank_series(
    refs: Sequence[ResourceRef],
    query: str,
    *,
    limit: int = 5,
    include_localizers: bool = False,
) -> dict[str, Any]:
    """Rank DICOM refs for ``query``; ``selected`` is set only when confident."""
    intent = parse_query_intent(query)
    pool = list(refs)
    if not include_localizers:
        acquisitions = [
            ref
            for ref in pool
            if str(ref.meta.get("series_kind") or "acquisition") != "localizer"
        ]
        if acquisitions:
            pool = acquisitions
    if intent.modalities:
        matching = [
            ref
            for ref in pool
            if str(ref.meta.get("Modality") or "").upper() in intent.modalities
            or (
                intent.contours
                and str(ref.meta.get("series_kind") or "") in _CONTOUR_KINDS
            )
        ]
        if matching:
            pool = matching

    ranked = [_score_ref(ref, intent) for ref in pool]
    by_id = {ref.id: ref for ref in pool}
    ranked.sort(key=lambda item: _rank_sort_key(item, by_id[item["id"]], intent))
    candidates = ranked[: max(1, int(limit))]
    selected = candidates[0] if candidates else None
    confident = _is_confident(selected, intent)
    return {
        "query": query,
        "intent": {
            "modalities": sorted(intent.modalities),
            "regions": sorted(intent.regions),
            "contours": intent.contours,
        },
        "confident": confident,
        "selected": selected if confident else None,
        "candidates": candidates,
    }


def _score_ref(ref: ResourceRef, intent: QueryIntent) -> dict[str, Any]:
    meta = ref.meta
    kind = str(meta.get("series_kind") or "acquisition")
    modality = str(meta.get("Modality") or "").upper()
    series_blob = _series_blob(meta)
    series_regions = infer_regions(series_blob)
    study_regions = infer_regions(_clean_text(meta.get("StudyDescription")))
    body_regions = infer_regions(_clean_text(meta.get("BodyPartExamined")))

    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    if kind == "localizer":
        score -= 100
        reasons.append("localizer/scout")
    elif kind == "calibration":
        score -= 80
        reasons.append("calibration")
    elif kind == "derived":
        score -= 50
        reasons.append("derived/non-diagnostic")
    elif kind in _CONTOUR_KINDS:
        if intent.contours:
            score += 50
            reasons.append("RT structure set" if kind == "rtstruct" else "segmentation")
        else:
            score -= 25
            reasons.append("contour object (no pixels of its own)")
    elif kind in _RT_KINDS:
        score -= 25
        reasons.append("RT object (no pixel data)")
    else:
        score += 5
        reasons.append("acquisition")
        if intent.contours:
            score -= 10
            reasons.append("image series (contours live on RTSTRUCT/SEG)")

    if intent.modalities:
        if modality in intent.modalities:
            score += 25
            reasons.append(f"modality {modality}")
        elif intent.contours and kind in _CONTOUR_KINDS:
            score += 20
            reasons.append("contours linked to image query")
        else:
            score -= 15
            reasons.append(f"modality mismatch ({modality})")

    if intent.regions:
        if intent.regions & series_regions:
            score += 30
            reasons.append("series anatomy match")
        elif "extremity" in series_regions and intent.regions & _ORGAN_REGIONS:
            score -= 40
            reasons.append("series is runoff/extremity")
            warnings.append(
                "series protocol is runoff/extremity; BodyPartExamined is not trusted"
            )
        elif intent.regions & study_regions:
            score += 10
            reasons.append("study anatomy match")

        if "extremity" not in series_regions and intent.regions & body_regions:
            score += 5
            reasons.append("BodyPartExamined match")
        elif "extremity" in series_regions and intent.regions & body_regions:
            reasons.append("ignored BodyPartExamined (series text is extremity/runoff)")

        if (
            _has_word(series_blob, "delay")
            and "extremity" in (series_regions | study_regions)
            and intent.regions & _ORGAN_REGIONS
        ):
            score -= 15
            reasons.append("delay phase on runoff")

    n = _as_int(meta.get("instance_count"), 0)
    if n >= 10:
        score += 5
    elif n <= 1 and kind == "acquisition":
        score -= 10
        reasons.append("single frame")
    if n >= 800:
        score -= 4
        reasons.append("very large stack")

    z_span = _as_float(meta.get("z_span_mm"))
    if intent.regions & _ORGAN_REGIONS and z_span is not None and z_span >= LONG_FOV_MM:
        score -= 10
        reasons.append("long-FOV series")

    payload: dict[str, Any] = {
        "id": ref.id,
        "label": ref.label,
        "Modality": modality or None,
        "series_kind": kind,
        "instance_count": n,
        "SeriesDescription": meta.get("SeriesDescription"),
        "ProtocolName": meta.get("ProtocolName"),
        "StudyDescription": meta.get("StudyDescription"),
        "BodyPartExamined": meta.get("BodyPartExamined"),
        "suggested_slice_index": suggested_slice_index(meta, regions=intent.regions),
        "score": round(score, 2),
        "reasons": reasons,
        "warnings": warnings,
    }
    roi_names = meta.get("roi_names")
    if roi_names:
        payload["roi_names"] = list(roi_names)[:20]
        payload["preferred_roi"] = meta.get("preferred_roi")
    return payload


def _is_confident(selected: Mapping[str, Any] | None, intent: QueryIntent) -> bool:
    if not selected:
        return False
    kind = str(selected.get("series_kind") or "")
    if kind in {"localizer", "calibration", "derived"}:
        return False
    modality = str(selected.get("Modality") or "").upper()
    if intent.modalities and modality not in intent.modalities:
        if not (intent.contours and kind in _CONTOUR_KINDS):
            return False
    if float(selected.get("score") or 0) < 0:
        # An explicit modality ("CT slice") still selects the best matching
        # acquisition even when anatomy tags conflict (runoff vs liver).
        return bool(intent.modalities and modality in intent.modalities)
    return True


def _rank_sort_key(
    item: Mapping[str, Any], ref: ResourceRef, intent: QueryIntent
) -> tuple[float, float, int, str]:
    """Higher score first; for organ queries, more-superior coverage next."""
    z_sup = _as_float(ref.meta.get("z_superior_mm"))
    organ_tie = z_sup if (intent.regions & _ORGAN_REGIONS and z_sup is not None) else 0.0
    return (
        -float(item["score"]),
        -organ_tie,
        -_as_int(item.get("instance_count"), 0),
        str(item["id"]),
    )


def _primary_region(intent: QueryIntent | None) -> str | None:
    if intent is None:
        return None
    for region in _REGION_PRIORITY:
        if region in intent.regions:
            return region
    return None


def _series_blob(meta: Mapping[str, Any]) -> str:
    parts = [
        _clean_text(meta.get("SeriesDescription")),
        _clean_text(meta.get("ProtocolName")),
    ]
    names = meta.get("roi_names") or []
    if names:
        parts.append(" ".join(str(name).lower() for name in names[:20] if name))
    return " ".join(part for part in parts if part)


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None


def _clean_text(value: Any) -> str:
    text = str(value).strip().lower() if value is not None else ""
    return "" if text in {"", "nan", "none"} else text


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None
