"""Series ranking for the imaging specialist, and one read with the vision call faked."""

from __future__ import annotations

import pytest
from meddataos.datactrl import Case
from meddataos.datactrl.types import Modality, ResourceRef
from meddataos.datactrl.utils.dicom_meta import ABDOMEN_FROM_SUPERIOR_MM

from meddataos.specialists.common import case_root, has_case
from meddataos.specialists.imaging import read
from meddataos.specialists.imaging.select import (
    choose_preview_window,
    parse_query_intent,
    rank_series,
)


def _ref(key: str, **meta) -> ResourceRef:
    return ResourceRef(
        id=f"dicom:{key}",
        modality=Modality.DICOM,
        label=str(meta.get("SeriesDescription") or key),
        meta=meta,
    )


def _abdomen_index(z_first: float, z_last: float, n: int) -> int:
    target = max(z_first, z_last) - ABDOMEN_FROM_SUPERIOR_MM
    return int(round((target - z_first) / (z_last - z_first) * (n - 1)))


def _runoff_refs() -> list[ResourceRef]:
    runoff = dict(
        Modality="CT",
        ProtocolName="AP_RUNOFF",
        StudyDescription="CT ANGIO ABD/PELVIS W RUNOFFS",
        BodyPartExamined="LIVER",
        series_kind="acquisition",
        z_first_mm=-174.0,
        z_last_mm=-1510.0,
        z_span_mm=1336.0,
        z_superior_mm=-174.0,
    )
    return [
        _ref(
            "topogram",
            Modality="CT",
            SeriesDescription="Topogram 0.6 T20s",
            series_kind="localizer",
            instance_count=1,
            BodyPartExamined="LIVER",
        ),
        _ref("runoff5", SeriesDescription="AP Runoff 5.0 B41f", instance_count=268, **runoff),
        _ref("runoff1", SeriesDescription="AP Runoff 1.0 B31f", instance_count=1338, **runoff),
        _ref(
            "delay",
            Modality="CT",
            SeriesDescription="Delay 5.0 B31f",
            ProtocolName="AP_RUNOFF",
            StudyDescription="CT ANGIO ABD/PELVIS W RUNOFFS",
            BodyPartExamined="LIVER",
            series_kind="acquisition",
            instance_count=125,
            z_first_mm=-889.0,
            z_last_mm=-1510.0,
            z_span_mm=621.0,
            z_superior_mm=-889.0,
        ),
        _ref(
            "lava",
            Modality="MR",
            SeriesDescription="AX LAVA",
            ProtocolName="liver",
            StudyDescription="MR ABDOMEN W/WO CONTRAST",
            BodyPartExamined="LIVER",
            series_kind="acquisition",
            instance_count=88,
            z_first_mm=-80.0,
            z_last_mm=-280.0,
            z_span_mm=200.0,
            z_superior_mm=-80.0,
        ),
    ]


def _hnc_refs() -> list[ResourceRef]:
    return [
        _ref(
            "neck",
            Modality="CT",
            SeriesDescription="Neck 2.0 CE",
            ProtocolName="Head and Neck",
            StudyDescription="Research HNC Planning CT",
            series_kind="acquisition",
            instance_count=181,
            z_first_mm=-792.0,
            z_last_mm=-1152.0,
            z_span_mm=360.0,
            z_superior_mm=-792.0,
        ),
        _ref(
            "rt",
            Modality="RTSTRUCT",
            SeriesDescription="",
            series_kind="rtstruct",
            instance_count=1,
            roi_names=["SpinalCord", "Esophagus", "GTVp", "Larynx", "EXTERNAL"],
            preferred_roi="GTVp",
            ReferencedSeriesUID="neck-uid",
        ),
    ]


def test_intent_reads_modality_region_and_contours():
    intent = parse_query_intent(
        "What did the hep clinic note say, and what does a representative CT slice show?"
    )
    assert "CT" in intent.modalities and "abdomen" in intent.regions

    neck = parse_query_intent("representative CT slice of the neck")
    assert "neck" in neck.regions and not neck.contours

    contours = parse_query_intent("Which structures are contoured on the planning CT, is there a GTV?")
    assert contours.contours and "CT" in contours.modalities

    assert "SEG" in parse_query_intent("show the segmentation").modalities


def test_liver_mri_beats_runoff_ct_for_an_organ_query():
    result = rank_series(_runoff_refs(), "liver lesion on MRI")
    assert result["confident"]
    assert result["selected"]["id"] == "dicom:lava"


def test_ct_query_skips_localizer_and_aims_near_the_superior_end():
    query = "What did the hep clinic note say, and what does a representative CT slice show?"
    result = rank_series(_runoff_refs(), query)
    selected = result["selected"]
    assert result["confident"]
    assert selected["id"] == "dicom:runoff5"
    assert selected["suggested_slice_index"] == _abdomen_index(-174.0, -1510.0, 268)
    assert selected["suggested_slice_index"] != 268 // 2
    assert any("runoff" in reason or "extremity" in reason for reason in selected["reasons"])
    assert "dicom:topogram" not in [item["id"] for item in result["candidates"]]


def test_body_part_tag_does_not_override_runoff_series_text():
    assert rank_series(_runoff_refs(), "hepatic mass")["selected"]["id"] == "dicom:lava"


def test_contour_question_selects_the_structure_set():
    result = rank_series(_hnc_refs(), "which structures are contoured on the planning CT")
    assert result["confident"] and result["selected"]["id"] == "dicom:rt"
    assert "GTVp" in result["selected"]["roi_names"]


def test_plain_ct_question_skips_the_structure_set():
    result = rank_series(_hnc_refs(), "representative CT slice of the neck")
    assert result["confident"] and result["selected"]["id"] == "dicom:neck"


def test_no_matching_modality_is_not_a_confident_pick():
    result = rank_series(_runoff_refs(), "what does the PET show")
    assert not result["confident"] and result["selected"] is None


def test_preview_window_follows_anatomy_and_modality():
    window = lambda modality, text: choose_preview_window(modality, parse_query_intent(text))  # noqa: E731
    assert window("MR", "liver") == "minmax"
    assert window("PT", "whole body") == "pet"
    assert window("CT", "liver CT") == "liver"
    assert window("CT", "chest CT") == "lung"
    assert window("CT", "brain CT") == "brain"
    assert window("CT", "representative CT") == "abdomen"
    assert window("CT", "larynx CT") == "abdomen"


needs_radcure = pytest.mark.skipif(not has_case("RADCURE-0006"), reason="data/RADCURE-0006 not available")


@pytest.fixture
def no_vision(monkeypatch):
    monkeypatch.setattr(read, "_describe_slice", lambda png, prompt: "Fake read of one slice.")


@needs_radcure
def test_read_slice_cites_the_ct_series_for_an_image_question(no_vision):
    case = Case.open(case_root("RADCURE-0006"))
    result = read.read_slice(case, "representative CT slice of the neck")
    assert "Neck 2.0 CE" in result.series_path
    assert result.preview["overlay"] is False and result.preview["slice_index"] is not None


@needs_radcure
def test_read_slice_follows_the_contours_for_a_structure_question(no_vision):
    case = Case.open(case_root("RADCURE-0006"))
    result = read.read_slice(case, "which structures are contoured on the planning CT, is there a GTV?")
    assert result.preview["overlay"] is True
    assert result.series_id.startswith("dicom:")


@needs_radcure
def test_read_slice_fails_closed_when_no_series_fits(no_vision):
    case = Case.open(case_root("RADCURE-0006"))
    result = read.read_slice(case, "what does the PET show")
    assert result.series_path == "" and result.preview is None
    assert "No confident DICOM series match" in result.summary


def test_slice_is_described_by_the_azure_deployment_when_configured(monkeypatch):
    for name, value in {
        "AZURE_OPENAI_API_KEY": "k",
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
        "AZURE_OPENAI_DEPLOYMENT": "vision",
    }.items():
        monkeypatch.setenv(name, value)
    sent = []

    def fake_chat(messages, **_):
        sent.append(messages)
        return {"content": " One axial slice through the neck. "}

    monkeypatch.setattr(read, "azure_chat", fake_chat)
    monkeypatch.setattr(read, "create_client", lambda: pytest.fail("Gemini must not be called"))

    assert read._describe_slice(b"png-bytes", "Describe it.") == "One axial slice through the neck."
    parts = sent[0][0]["content"]
    assert parts[0] == {"type": "text", "text": "Describe it."}
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


_AZURE_STYLE_REPLY = (
    "![CT neck preview, slice 90 of 181](dicom:1.3.6.1.4.1.14519.5.2.1.5235)\n\n"
    "**Series:** Neck 2.0 CE (CT) \u00b7 **Slice:** 90 of 181 \u00b7 **Window:** abdomen\n\n"
    "This single axial preview slice shows the upper neck and the pharyngeal airway. "
    "This is one preview slice, **not a complete study interpretation**.\n\n"
    "**Citation:** DICOM resource `dicom:1.3.6.1.4.1.14519.5.2.1.5235`, slice 90/181."
)


def test_description_drops_image_links_and_repeated_metadata():
    plain = read._plain(_AZURE_STYLE_REPLY)
    assert "![" not in plain and "dicom:" not in plain and "Series" not in plain
    assert plain.startswith("This single axial preview slice")
    assert read._plain("Slice 90 shows the airway.") == "Slice 90 shows the airway."


def test_marker_follows_words_even_when_the_text_has_dotted_numbers():
    from meddataos.specialists.imaging.serve import _mark

    marked = _mark("Series Neck 2.0 CE shows the airway. A second sentence.")
    assert marked == "Series Neck 2.0 CE shows the airway [cite:1]. A second sentence."
    # Even the raw model reply, with a UID in it, must not start with the marker.
    assert not _mark(_AZURE_STYLE_REPLY).lstrip().startswith("[cite:")
    assert _mark("No full stop here") == "No full stop here [cite:1]."
