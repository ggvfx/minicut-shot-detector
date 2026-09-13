"""
Tests for the Job Sidecar.

The sidecar is what makes a wrong boundary diagnosable months later, so these
check the two things that would undermine that: a file that cannot be read back
into the model, and a failed job quietly writing nothing.
"""

import json
from pathlib import Path

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import JobResult, Shot, SourceInfo, ValidationResult
from src.core.sidecar import (
    SIDECAR_SUFFIX,
    capture_environment,
    sidecar_path_for,
    write_sidecar,
)

# --- HELPERS ---


def make_result(passed: bool = True) -> JobResult:
    return JobResult(
        source=SourceInfo(
            path="D:/cuts/reel.mp4",
            width=1920,
            height=1080,
            fps_numerator=24,
            fps_denominator=1,
            frame_count=100,
            codec="h264",
            start_timecode="01:00:00:00",
        ),
        shots=[
            Shot(index=1, start_frame=0, end_frame=49, file="reel_shot_001.mp4"),
            Shot(index=2, start_frame=50, end_frame=99, file="reel_shot_002.mp4",
                 confidence=0.71, detectors_agreed=False),
        ],
        validation=ValidationResult(
            passed=passed,
            checks={"frames_sum": passed, "round_trip": passed},
            failures=[] if passed else ["Frame 37 differs between the mezzanine and the shots"],
        ),
        environment={"ffmpeg": "ffmpeg version 8.0.1", "app": "Minicut Shot Detector 0.1.0"},
    )


# --- NAMING ---


def test_sidecar_is_named_after_the_source(tmp_path):
    path = sidecar_path_for(Path("D:/cuts/CHAS_006_Edit_E.mp4"), tmp_path)

    assert path.name == f"CHAS_006_Edit_E{SIDECAR_SUFFIX}"
    assert path.parent == tmp_path


# --- WRITING ---


def test_sidecar_is_valid_json_with_the_shots_in_it(tmp_path):
    written = write_sidecar(make_result(), tmp_path / "reel_shots.json")
    data = json.loads(written.read_text(encoding="utf-8"))

    assert [shot["start_frame"] for shot in data["shots"]] == [0, 50]
    assert [shot["end_frame"] for shot in data["shots"]] == [49, 99]
    assert data["source"]["fps_numerator"] == 24
    assert data["source"]["start_timecode"] == "01:00:00:00"


def test_sidecar_reads_back_into_the_model(tmp_path):
    """
    The file has to survive a round trip, because the identifier tab will read
    it back. A sidecar that cannot be re-validated is a dead end.
    """
    written = write_sidecar(make_result(), tmp_path / "reel_shots.json")

    restored = JobResult.model_validate(json.loads(written.read_text(encoding="utf-8")))

    assert restored.shots[1].confidence == 0.71
    assert restored.shots[1].detectors_agreed is False
    assert restored.source.frame_count == 100


def test_a_failed_job_still_writes_its_sidecar(tmp_path):
    """
    A failed job's sidecar is the most useful thing to look at when working out
    why, so it is written whether or not validation passed.
    """
    written = write_sidecar(make_result(passed=False), tmp_path / "reel_shots.json")
    data = json.loads(written.read_text(encoding="utf-8"))

    assert data["validation"]["passed"] is False
    assert "Frame 37" in data["validation"]["failures"][0]


def test_missing_directories_are_created(tmp_path):
    written = write_sidecar(make_result(), tmp_path / "new" / "nested" / "reel_shots.json")

    assert written.is_file()


def test_review_flags_survive_into_the_file(tmp_path):
    """Which shots need a human eye is the point of recording confidence."""
    written = write_sidecar(make_result(), tmp_path / "reel_shots.json")
    data = json.loads(written.read_text(encoding="utf-8"))

    needs_review = [shot for shot in data["shots"] if not shot["detectors_agreed"]]
    assert [shot["index"] for shot in needs_review] == [2]


# --- ENVIRONMENT CAPTURE ---


def test_environment_records_what_produced_the_job():
    captured = capture_environment(MediaToolchain())

    assert "Minicut Shot Detector" in captured["app"]
    assert captured["platform"]
    assert captured["ffmpeg"]
    assert captured["ffprobe"]


def test_missing_tools_are_recorded_as_absent():
    """
    An absent tool is written down rather than left out.

    A sidecar missing a key cannot be told apart from one written by an older
    version of this tool.
    """
    captured = capture_environment(MediaToolchain(discover=False))

    assert captured["ffmpeg"] == "not found"
    assert captured["ffprobe"] == "not found"


def test_library_versions_are_recorded():
    """What detected the cuts has to be in the record, not just what cut them."""
    captured = capture_environment(MediaToolchain(discover=False))

    assert captured["scenedetect"], "the detector version should be recorded"
    assert captured["app"]
    assert captured["platform"]
