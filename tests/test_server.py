"""
Tests for the HTTP Routes.

Exercises the API through FastAPI's test client, so the JSON the front end
actually receives is what gets asserted.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from src.media.workspace import WORK_DIRECTORY
from src.ui.server import app

client = TestClient(app)


# --- PAGE AND STATIC FILES ---


def test_index_is_served():
    response = client.get("/")

    assert response.status_code == 200
    assert "Minicut Shot Detector" in response.text


# --- ENVIRONMENT ---


def test_the_splitter_panel_reports_what_a_split_needs():
    """
    Asserted by key rather than by count: a count says nothing about which row
    went missing, and this list has already changed three times.
    """
    response = client.get("/api/environment")

    assert response.status_code == 200
    report = response.json()

    assert report["overall"] in ("ok", "degraded", "blocked")
    assert [check["key"] for check in report["checks"]] == [
        "python",
        "ffmpeg",
        "ffprobe",
        "encoders",
        "scenedetect",
        "disk",
    ], "the splitter is never shown a model it does not use"


def test_the_identifier_panel_reports_its_models_instead():
    """
    The backend rows come from src/backends/, which core may not import — so
    the route is where the checker's own rows and those meet. They appear only
    here, and they gate: a user in this tab with no model can do nothing.
    """
    report = client.get("/api/environment", params={"tab": "identifier"}).json()
    keys = [check["key"] for check in report["checks"]]

    assert keys == ["python", "ffmpeg", "ffprobe", "disk", "backend_vision", "backend_text"]
    assert not any(check["advisory"] for check in report["checks"]), (
        "in this tab a missing model is a real block, not an aside"
    )


def test_an_unknown_tab_is_refused():
    assert client.get("/api/environment", params={"tab": "sideways"}).status_code == 422


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
    assert report["source"]["detected_crop"] is None
    assert report["free_gb"] is not None, "a chosen output directory should be measured"


def test_probe_reports_a_mask(clips):
    response = client.post("/api/probe", json={"source_path": str(clips["letterbox"])})

    assert response.json()["source"]["detected_crop"] == "320:180:0:30"


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


# --- SPLIT ---


def test_split_writes_shots_and_returns_the_job(clips, tmp_path):
    response = client.post(
        "/api/split",
        json={
            "source_path": str(clips["pal"]),
            "output_dir": str(tmp_path),
            "boundaries": ["20", "35"],
        },
    )

    assert response.status_code == 200
    job = response.json()

    assert job["validation"]["passed"] is True
    assert [shot["start_frame"] for shot in job["shots"]] == [0, 20, 35]
    assert all(Path(shot["file"]).is_file() for shot in job["shots"])


def test_boundaries_can_be_typed_as_timecodes(clips, tmp_path):
    """
    A timecode and a frame number can both name the same cut.

    Both are natural depending on whether the number came from a frame counter
    or an editor's timeline, so both are accepted. The pal clip starts at
    10:00:00:00, so this timecode is frame 20.
    """
    response = client.post(
        "/api/split",
        json={
            "source_path": str(clips["pal"]),
            "output_dir": str(tmp_path),
            "boundaries": ["10:00:00:20"],
        },
    )

    assert response.status_code == 200
    assert [shot["start_frame"] for shot in response.json()["shots"]] == [0, 20]


def test_no_boundaries_gives_one_shot(clips, tmp_path):
    response = client.post(
        "/api/split",
        json={"source_path": str(clips["pal"]), "output_dir": str(tmp_path), "boundaries": []},
    )

    assert response.status_code == 200
    assert len(response.json()["shots"]) == 1


def test_an_unreadable_boundary_is_422(clips, tmp_path):
    """The user can fix a typo, so it is a bad request rather than a failure."""
    response = client.post(
        "/api/split",
        json={
            "source_path": str(clips["pal"]),
            "output_dir": str(tmp_path),
            "boundaries": ["twenty"],
        },
    )

    assert response.status_code == 422
    assert "neither a frame number nor a timecode" in response.json()["detail"]


def test_a_boundary_past_the_end_is_422(clips, tmp_path):
    response = client.post(
        "/api/split",
        json={
            "source_path": str(clips["pal"]),
            "output_dir": str(tmp_path),
            "boundaries": ["9999"],
        },
    )

    assert response.status_code == 422
    assert "outside the source" in response.json()["detail"]


def test_a_refused_source_is_409(clips, tmp_path):
    """
    Variable frame rate is not the user mistyping something — the file itself
    cannot be cut accurately, which is a conflict rather than a bad request.
    """
    response = client.post(
        "/api/split",
        json={"source_path": str(clips["vfr"]), "output_dir": str(tmp_path), "boundaries": ["20"]},
    )

    assert response.status_code == 409
    assert "variable frame rate" in response.json()["detail"]


def test_split_missing_source_is_404(tmp_path):
    response = client.post(
        "/api/split",
        json={"source_path": str(tmp_path / "gone.mov"), "output_dir": str(tmp_path)},
    )

    assert response.status_code == 404


# --- WORKING FILES ---


def test_work_reports_nothing_for_a_clean_directory(tmp_path):
    response = client.get("/api/work", params={"output_dir": str(tmp_path)})

    assert response.status_code == 200
    assert response.json()["bytes"] == 0


def test_work_reports_what_is_reclaimable_and_clearing_frees_it(tmp_path):
    """
    The figure shown in the UI and the one clearing returns must agree.

    They come from the same measurement, and a "Clear" that frees less than it
    offered would be worse than not offering.
    """
    work_dir = tmp_path / WORK_DIRECTORY
    work_dir.mkdir()
    (work_dir / "reel_01_mezzanine.mp4").write_bytes(b"\0" * 5000)

    reported = client.get("/api/work", params={"output_dir": str(tmp_path)}).json()
    assert reported["bytes"] == 5000
    assert reported["sources"] == ["reel_01"]

    cleared = client.post("/api/work/clear", json={"output_dir": str(tmp_path)})
    assert cleared.status_code == 200
    assert cleared.json()["bytes"] == 5000

    assert client.get("/api/work", params={"output_dir": str(tmp_path)}).json()["bytes"] == 0


def test_work_leaves_the_open_source_alone(tmp_path):
    """
    Clearing while a source is open must not delete the mezzanine it will
    be split from.
    """
    work_dir = tmp_path / WORK_DIRECTORY
    work_dir.mkdir()
    (work_dir / "reel_01_mezzanine.mp4").write_bytes(b"\0" * 5000)
    (work_dir / "reel_02_mezzanine.mp4").write_bytes(b"\0" * 3000)

    params = {"output_dir": str(tmp_path), "source_path": "D:/media/reel_01.mp4"}
    assert client.get("/api/work", params=params).json()["bytes"] == 3000

    client.post(
        "/api/work/clear",
        json={"output_dir": str(tmp_path), "source_path": "D:/media/reel_01.mp4"},
    )

    assert (work_dir / "reel_01_mezzanine.mp4").is_file()
    assert not (work_dir / "reel_02_mezzanine.mp4").exists()


# --- IDENTIFIER: PRODUCTION KNOWLEDGE ---


def test_knowledge_reports_what_the_production_folder_holds():
    """
    The panel says what was found; the text itself is for the model.

    Sizes rather than contents, because a character bible would make this
    response enormous for no reason anybody can read.
    """
    report = client.get("/api/knowledge").json()

    assert "directory" in report
    for name in ("characters", "terminology"):
        assert isinstance(report[name]["found"], bool)
        assert isinstance(report[name]["characters"], int)
        assert "text" not in report[name], "contents never cross the wire"


# --- SETUP GUIDE ---


def test_the_guide_says_what_to_install_whatever_the_machine_has():
    """
    Separate from the checks on purpose.

    Those only speak up when something is missing, which is right for a status
    panel and useless for setting up a second machine or telling a colleague
    what they will need.
    """
    guide = client.get("/api/guide").json()

    assert guide["platform"]
    for item in ("python", "ffmpeg"):
        assert guide[item]["label"]
        assert guide[item]["fixes"], f"{item} must say how to install it"
        assert all(
            step["command"] or step["url"] for step in guide[item]["fixes"]
        ), "every option gives something to act on"

    assert any(step["url"] for step in guide["ffmpeg"]["fixes"]), (
        "always a route that needs no package manager"
    )
