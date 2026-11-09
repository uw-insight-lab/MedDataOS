"""Gemini client and model names used by the specialists."""

from __future__ import annotations

import os

import meddataos.specialists.common  # noqa: F401  (loads .env)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Notes: per-note extraction and OCR versus query-time reasoning.
NOTES_EXTRACT_MODEL = os.getenv("NOTES_EXTRACT_MODEL", GEMINI_MODEL)
NOTES_REASON_MODEL = os.getenv("NOTES_REASON_MODEL", GEMINI_MODEL)


def create_client():
    """Create a Gemini API client from GEMINI_API_KEY."""
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Put it in .env or the environment.")
    return genai.Client(api_key=api_key)
