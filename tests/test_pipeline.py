"""
Tests for the Splitter Pipeline.

The pipeline holds no logic of its own, so what is tested here is the joining:
that a refused source stops the job, that a broken shot list stops it before
any transcoding, that the mezzanine survives a failure and not a success, and
that one call really does take a source to finished shots.
"""

import json
from pathlib import Path

import pytest

from src.core.config import ProjectConfig
from src.core.models import Boundary
from src.media.probe import SourceProbe
from src.pipeline import WORK_DIRECTORY, SplitterPipeline, clear_work, reclaimable_work

# --- HELPERS ---


def run_job(toolchain, source_path, output_dir, frames=(), full_round_trip=False):
    config = ProjectConfig(
        source_path=str(source_path),
        output_dir=str(output_dir),
        full_round_trip=full_round_trip,
    )
    pipeline = SplitterPipeline(config, toolchain)
    return pipeline.run([Boundary(frame=frame) for frame in frames])


# --- A COMPLETE JOB ---


def test_a_job_writes_shots_that_cover_the_source(toolchain, clips, tmp_path):
    """One call takes a source and a boundary list to finished shots."""
    result = run_job(toolchain, clips["pal"], tmp_path, frames=(20, 35))

    assert result.validation.passed is True
    assert len(result.shots) == 3

    probe = SourceProbe(toolchain)
    total = 0
    for shot in result.shots:
        written = Path(shot.file)
        assert written.is_file(), f"shot {shot.index} was not written"
        total += probe.probe(written).frame_count

    assert total == result.source.frame_count


def test_a_job_with_no_boundaries_produces_one_shot(toolchain, clips, tmp_path):
    """A source with no cuts is still a legitimate job, not an error."""
    result = run_job(toolchain, clips["pal"], tmp_path)

    assert len(result.shots) == 1
    assert result.validation.passed is True


def test_the_sidecar_is_written_next_to_the_shots(toolchain, clips, tmp_path):
    result = run_job(toolchain, clips["pal"], tmp_path, frames=(25,))

    sidecar = Path(result.sidecar_path)
    assert sidecar.parent == tmp_path

    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["validation"]["passed"] is True
    assert len(data["shots"]) == 2


def test_a_passing_job_removes_the_mezzanine(toolchain, clips, tmp_path):
    """The intermediate is not part of the delivery."""
    result = run_job(toolchain, clips["pal"], tmp_path, frames=(25,))

    assert result.mezzanine_path is None
    assert not any(path.name.endswith("_mezzanine.mov") for path in tmp_path.iterdir())


def test_the_work_directory_does_not_survive(toolchain, clips, tmp_path):
    """Scratch space for the round trip is cleaned up either way."""
    run_job(toolchain, clips["pal"], tmp_path, frames=(25,), full_round_trip=True)

    assert not (tmp_path / WORK_DIRECTORY).exists()


def test_the_full_round_trip_can_be_asked_for(toolchain, clips, tmp_path):
    """The stricter check is a setting the caller chooses, not a default."""
    result = run_job(toolchain, clips["pal"], tmp_path, frames=(25,), full_round_trip=True)

    assert result.validation.checks["round_trip"] is True
    assert "boundary_frames" not in result.validation.checks


def test_the_environment_is_recorded(toolchain, clips, tmp_path):
    """Every job records what produced it, for months-later diagnosis."""
    result = run_job(toolchain, clips["pal"], tmp_path, frames=(25,))

    assert "Minicut Shot Detector" in result.environment["app"]
    assert result.environment["ffmpeg"]


def test_h265_runs_end_to_end(toolchain, clips, tmp_path):
    result = run_job(toolchain, clips["h265"], tmp_path, frames=(12, 30))

    assert result.validation.passed is True
    assert result.source.codec == "hevc"
    assert all(Path(shot.file).suffix == ".mp4" for shot in result.shots)


# --- STOPPING EARLY ---


def test_a_variable_frame_rate_source_is_refused(toolchain, clips, tmp_path):
    """
    The refusal happens before any transcoding, and keeps its own wording.

    That message already tells the user what to do about it.
    """
    with pytest.raises(RuntimeError, match="variable frame rate"):
        run_job(toolchain, clips["vfr"], tmp_path, frames=(20,))

    assert list(tmp_path.iterdir()) == [], "nothing should be written for a refused source"


def test_a_boundary_past_the_end_stops_the_job(toolchain, clips, tmp_path):
    """Caught in the arithmetic, before an hour of transcoding."""
    with pytest.raises(ValueError, match="outside the source"):
        run_job(toolchain, clips["pal"], tmp_path, frames=(9999,))

    assert list(tmp_path.iterdir()) == []


def test_a_missing_source_is_reported_clearly(toolchain, tmp_path):
    with pytest.raises(FileNotFoundError):
        run_job(toolchain, tmp_path / "not-here.mov", tmp_path)


def test_a_config_without_a_source_names_the_missing_setting(toolchain, tmp_path):
    pipeline = SplitterPipeline(ProjectConfig(output_dir=str(tmp_path)), toolchain)

    with pytest.raises(ValueError, match="source"):
        pipeline.run([])


def test_a_config_without_an_output_directory_names_it(toolchain, clips):
    pipeline = SplitterPipeline(
        ProjectConfig(source_path=str(clips["pal"]), output_dir=""), toolchain
    )

    with pytest.raises(ValueError, match="output directory"):
        pipeline.run([])


# --- RECLAIMING WORKING FILES ---


def work_file(output_dir: Path, name: str, size: int = 1024) -> Path:
    """A file of a given size in the work folder, as an analysis would leave."""
    work_dir = output_dir / WORK_DIRECTORY
    work_dir.mkdir(exist_ok=True)

    path = work_dir / name
    path.write_bytes(b"\0" * size)
    return path


def test_nothing_is_reclaimable_without_a_work_folder(tmp_path):
    """An output directory nothing has run in yet has nothing to clear."""
    assert reclaimable_work(tmp_path) == []


def test_everything_is_reclaimable_when_no_source_is_open(tmp_path):
    """
    Before anything is analysed, every leftover is fair game.

    This is the case the button exists for: files left by a session that was
    closed without splitting.
    """
    work_file(tmp_path, "reel_01_mezzanine.mp4")
    work_file(tmp_path, "reel_01_proxy.mp4")

    assert len(reclaimable_work(tmp_path)) == 2


def test_the_open_source_is_never_offered_up(tmp_path):
    """
    The mezzanine of the source being reviewed is what the split cuts from.

    Offering it for deletion would break the next step the user takes.
    """
    work_file(tmp_path, "reel_01_mezzanine.mp4")
    work_file(tmp_path, "reel_01_proxy.mp4")
    work_file(tmp_path, "reel_02_mezzanine.mp4")

    reclaimable = reclaimable_work(tmp_path, keep_source=Path("D:/media/reel_01.mp4"))

    assert [path.name for path in reclaimable] == ["reel_02_mezzanine.mp4"]


def test_a_longer_name_starting_with_the_open_one_is_still_reclaimable(tmp_path):
    """
    "reel_02" must not claim "reel_02_extra"'s files.

    Matching on a name prefix would spare the wrong mezzanine here and leave
    the user wondering why clearing freed less than it said it would.
    """
    work_file(tmp_path, "reel_02_mezzanine.mp4")
    work_file(tmp_path, "reel_02_extra_mezzanine.mp4")

    reclaimable = reclaimable_work(tmp_path, keep_source=Path("reel_02.mp4"))

    assert [path.name for path in reclaimable] == ["reel_02_extra_mezzanine.mp4"]


def test_clearing_reports_the_bytes_it_freed(tmp_path):
    """The figure shown to the user has to be what actually went."""
    work_file(tmp_path, "reel_01_mezzanine.mp4", size=4096)
    work_file(tmp_path, "reel_01_proxy.mp4", size=2048)

    assert clear_work(tmp_path) == 6144
    assert reclaimable_work(tmp_path) == []


def test_clearing_removes_the_work_folder_when_it_empties(tmp_path):
    """An output directory that is finished with should look finished with."""
    work_file(tmp_path, "reel_01_mezzanine.mp4")

    clear_work(tmp_path)

    assert not (tmp_path / WORK_DIRECTORY).exists()


def test_clearing_keeps_the_folder_while_the_open_source_needs_it(tmp_path):
    """The folder stays as long as anything is still using it."""
    work_file(tmp_path, "reel_01_mezzanine.mp4")
    work_file(tmp_path, "reel_02_mezzanine.mp4")

    clear_work(tmp_path, keep_source=Path("reel_01.mp4"))

    assert (tmp_path / WORK_DIRECTORY / "reel_01_mezzanine.mp4").is_file()


def test_round_trip_scratch_belongs_to_nobody_and_always_goes(tmp_path):
    """
    `concat.txt` and `rejoined.mp4` are named after no source.

    They must not be spared by whichever source happens to be open.
    """
    work_file(tmp_path, "concat.txt")
    work_file(tmp_path, "rejoined.mp4")

    reclaimable = reclaimable_work(tmp_path, keep_source=Path("reel_01.mp4"))

    assert len(reclaimable) == 2
