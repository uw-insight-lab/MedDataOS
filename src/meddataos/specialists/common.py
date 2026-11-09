"""Paths, environment, and case lookup shared by the specialists."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from meddataos.datactrl import Case

REPO = Path(__file__).resolve().parents[3]

# Local cases live under <repo>/data/<patient_id> unless MEDDATA_CASES says otherwise.
CASES_DIR = Path(os.getenv("MEDDATA_CASES", REPO / "data")).expanduser()

# Disk caches (note ledgers). Ignored by git.
CACHE_DIR = Path(os.getenv("SPECIALISTS_CACHE", REPO / ".cache" / "specialists")).expanduser()

load_dotenv(REPO / ".env")

_LOCK = threading.Lock()
_CASES: dict[str, Case] = {}


def case_root(patient_id: str) -> Path:
    return CASES_DIR / patient_id


def has_case(patient_id: str) -> bool:
    return case_root(patient_id).is_dir()


def get_case(patient_id: str) -> Case:
    """Return a cached Case for ``patient_id``, opening it on first use."""
    if not has_case(patient_id):
        raise KeyError(f"No case folder for {patient_id!r} under {CASES_DIR}")
    with _LOCK:
        case = _CASES.get(patient_id)
        if case is None:
            case = _CASES[patient_id] = Case.open(case_root(patient_id))
        return case
