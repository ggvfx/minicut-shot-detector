"""
Tests for the HTTP Routes.

Exercises the API through FastAPI's test client, so the JSON the front end
actually receives is what gets asserted.
"""

import json
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
        "filters",
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
    The panel says what was found, by category; the text itself is for the
    model and never crosses the wire.
    """
    report = client.get("/api/knowledge").json()

    assert report["directory"]
    assert report["file"].endswith(".md")
    assert isinstance(report["found"], bool)
    assert isinstance(report["counts"], dict)
    assert report["categories"] == ["characters", "props", "environments"]


def test_the_film_terminology_never_reaches_the_user():
    """
    It ships with the app and changes almost never. Putting it in front of
    someone would only invite editing the one thing that does not need it.
    """
    body = client.get("/api/knowledge").text

    assert "terminology" not in body.lower()
    assert "OTS" not in body


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


# --- DESCRIBING A FOLDER, ROW BY ROW ---


def test_the_stream_sends_a_total_then_one_line_per_shot(monkeypatch):
    """
    The table draws a row per line and sizes its progress bar from the first
    one, so the shape of this response is a contract, not an implementation
    detail.
    """
    from src.core.models import ShotRecord
    from src.ui.routes import identifier as routes

    records = [ShotRecord(file=f"shot_{n}.mp4") for n in range(1, 4)]

    monkeypatch.setattr(routes.IdentifierPipeline, "shots", lambda _self: records)
    monkeypatch.setattr(
        routes.IdentifierPipeline, "prepare_stream", lambda _self, **_options: iter(records)
    )

    response = client.post("/api/identify/describe/stream", json={"shots_dir": "anywhere"})

    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]

    assert lines[0] == {"total": 3}
    assert len(lines) == 4, "a header line and one line per shot"
    assert [line["file"] for line in lines[1:]] == ["shot_1.mp4", "shot_2.mp4", "shot_3.mp4"]


def test_a_stream_that_cannot_start_says_so_in_the_body(monkeypatch):
    """
    The response has already begun by the time most failures can happen, so a
    status code is not available to carry them. An empty folder is reported as
    a final line the table can show, rather than a stream that simply stops.
    """
    from src.ui.routes import identifier as routes

    def no_shots(_self):
        raise RuntimeError("No video files in that folder")

    monkeypatch.setattr(routes.IdentifierPipeline, "shots", no_shots)

    response = client.post("/api/identify/describe/stream", json={"shots_dir": "anywhere"})

    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line]

    assert lines == [{"error": "No video files in that folder"}]


# --- NAMING, RENAMING AND EXPORT THROUGH THE API ---


def test_numbering_a_batch_proposes_names_and_writes_nothing(tmp_path):
    """
    The numbers arrive in the table before any file is touched — the whole
    point of a proposal is that forty rows can be read before one is applied.
    """
    files = []
    for index in (1, 2, 3):
        path = tmp_path / f"shot_{index:03d}.mp4"
        path.write_bytes(b"x")
        files.append({"file": str(path)})

    response = client.post("/api/identify/number", json={
        "records": files,
        "scheme": {
            "prefix": "PARA_003_",
            "start": "4560",
            "increment": 20,
            "suffix": "_blockout_v0001",
        },
    })

    assert response.status_code == 200
    assert [record["shot_number"] for record in response.json()] == [
        "PARA_003_4560_blockout_v0001",
        "PARA_003_4580_blockout_v0001",
        "PARA_003_4600_blockout_v0001",
    ]
    assert sorted(path.name for path in tmp_path.glob("*.mp4")) == [
        "shot_001.mp4", "shot_002.mp4", "shot_003.mp4"
    ], "a proposal renamed something"


def test_an_unsafe_rename_is_refused_with_the_reason(tmp_path):
    """409 rather than 422: the request is fine, the folder is not what it was."""
    for index in (1, 2):
        (tmp_path / f"shot_{index:03d}.mp4").write_bytes(b"x")

    records = [
        {"file": str(tmp_path / f"shot_{index:03d}.mp4"),
         "shot_number": "SAME", "approved": True}
        for index in (1, 2)
    ]

    response = client.post("/api/identify/rename", json={
        "records": records, "shots_dir": str(tmp_path),
    })

    assert response.status_code == 409
    assert "would both become" in response.json()["detail"]
    assert (tmp_path / "shot_001.mp4").is_file(), "a refused plan renamed something"


def test_a_rename_can_be_undone_through_the_api(tmp_path):
    path = tmp_path / "shot_001.mp4"
    path.write_bytes(b"x")
    records = [{"file": str(path), "shot_number": "SEQ_0010", "approved": True}]

    renamed = client.post("/api/identify/rename", json={
        "records": records, "shots_dir": str(tmp_path),
    })
    assert renamed.status_code == 200
    assert (tmp_path / "SEQ_0010.mp4").is_file()

    undone = client.post("/api/identify/rename/undo", json={
        "records": records, "shots_dir": str(tmp_path),
    })

    assert undone.json() == {"restored": 1}
    assert path.is_file()


def test_exporting_writes_both_formats_beside_the_shots(tmp_path):
    """One press, both files. Nobody should have to come back for the other one."""
    path = tmp_path / "shot_001.mp4"
    path.write_bytes(b"x")

    response = client.post("/api/identify/export", json={
        "records": [{"file": str(path), "shot_number": "SEQ_0010"}],
        "shots_dir": str(tmp_path),
        "thumbnails": False,
    })

    assert response.status_code == 200
    written = response.json()
    folder = Path(written["folder"])

    assert (folder / written["csv"]).is_file()
    assert (folder / written["xlsx"]).is_file()


def test_a_clip_is_served_in_the_range_a_browser_asked_for(tmp_path):
    """Without ranges a clip plays but cannot be scrubbed, which is what review is."""
    path = tmp_path / "shot_001.mp4"
    path.write_bytes(b"0123456789")

    response = client.get(
        "/api/identify/clip",
        params={"path": str(path)},
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"


def test_a_clip_asked_for_whole_is_served_whole(tmp_path):
    path = tmp_path / "shot_001.mp4"
    path.write_bytes(b"0123456789")

    response = client.get("/api/identify/clip", params={"path": str(path)})

    assert response.status_code == 200
    assert response.content == b"0123456789"


def test_anything_that_is_not_a_clip_is_a_404(tmp_path):
    """
    The table asks for files by path, so the route answers for shots and
    nothing else — a 404 that says nothing about what is on the disk.
    """
    secret = tmp_path / "passwords.txt"
    secret.write_text("nope", encoding="utf-8")

    response = client.get("/api/identify/clip", params={"path": str(secret)})

    assert response.status_code == 404


def test_a_shot_with_no_sampled_frame_has_no_poster(tmp_path):
    path = tmp_path / "shot_001.mp4"
    path.write_bytes(b"x")

    response = client.get("/api/identify/poster", params={"path": str(path)})

    assert response.status_code == 404
