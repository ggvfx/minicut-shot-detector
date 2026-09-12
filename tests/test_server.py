"""
Tests for the HTTP Routes.

Exercises the API through FastAPI's test client, so the JSON the front end
actually receives is what gets asserted.
"""

import pytest
from fastapi.testclient import TestClient

from src.ui.server import app

client = TestClient(app)


# --- PAGE AND STATIC FILES ---


def test_index_is_served():
    response = client.get("/")

    assert response.status_code == 200
    assert "Minicut Shot Detector" in response.text


# --- ENVIRONMENT ---


def test_environment_reports_every_check():
    response = client.get("/api/environment")

    assert response.status_code == 200
    report = response.json()
    assert report["overall"] in ("ok", "degraded", "blocked")
    assert len(report["checks"]) == 9


# --- BROWSE ---


def test_browse_lists_a_directory(tmp_path):
    (tmp_path / "shots").mkdir()
    (tmp_path / "reel.mov").write_bytes(b"x")

    response = client.get("/api/browse", params={"path": str(tmp_path)})

    assert response.status_code == 200
    names = [entry["name"] for entry in response.json()["entries"]]
    assert names == ["shots", "reel.mov"]


def test_browse_rejects_a_file(tmp_path):
    target = tmp_path / "reel.mov"
    target.write_bytes(b"x")

    assert client.get("/api/browse", params={"path": str(target)}).status_code == 404


# --- PROBE ---


def test_probe_returns_source_facts(clips, tmp_path):
    """The full report the source panel renders."""
    response = client.post(
        "/api/probe",
        json={"source_path": str(clips["pal"]), "output_dir": str(tmp_path)},
    )

    assert response.status_code == 200
    report = response.json()

    assert report["source"]["fps_numerator"] == 25
    assert report["source"]["frame_count"] == 50
    assert report["source"]["start_timecode"] == "10:00:00:00"
    assert report["duration_timecode"] == "00:00:02:00", "duration is a length, not a position"
    assert report["can_split"] is True
    assert report["detected_crop"] is None
    assert report["free_gb"] is not None, "a chosen output directory should be measured"


def test_probe_reports_a_mask(clips):
    response = client.post("/api/probe", json={"source_path": str(clips["letterbox"])})

    assert response.json()["detected_crop"] == "320:180:0:30"


def test_probe_refuses_variable_frame_rate(clips):
    """VFR is a refusal, not a warning — boundaries cannot be trusted at all."""
    response = client.post("/api/probe", json={"source_path": str(clips["vfr"])})

    assert response.status_code == 200
    report = response.json()

    assert report["can_split"] is False
    assert "variable frame rate" in report["refusal_reason"]


def test_probe_missing_file_is_404(tmp_path):
    response = client.post("/api/probe", json={"source_path": str(tmp_path / "gone.mov")})

    assert response.status_code == 404


def test_probe_non_video_is_422(clips):
    """An audio-only file is a bad request, not a server error."""
    response = client.post("/api/probe", json={"source_path": str(clips["audio_only"])})

    assert response.status_code == 422
    assert "No video stream" in response.json()["detail"]
