"""
Tests for the Pixel Checks.

These run after cutting and decode frames to do their work, so every case here
is a failure no frame count could see: a shot taken from the wrong place, a
file holding another shot's content, a dropped or reordered shot.

The arithmetic half is covered by test_integrity.py, which needs no ffmpeg.
"""

import pytest

from src.core.models import Shot
from src.media.mezzanine import MezzanineBuilder
from src.media.probe import SourceProbe
from src.media.splitter import ShotSplitter
from src.validation.validator import (
    CHECK_BOUNDARY_FRAMES,
    CHECK_ROUND_TRIP,
    JobValidator,
)

# --- HASH COMPARISON (pure logic) ---


def test_identical_hashes_pass():
    assert JobValidator._compare_frame_hashes(["a", "b", "c"], ["a", "b", "c"]) == (True, None)


def test_a_missing_frame_is_reported_with_the_count():
    """A dropped frame at a cut is exactly what this check exists to find."""
    passed, failure = JobValidator._compare_frame_hashes(["a", "b", "c"], ["a", "b"])

    assert passed is False
    assert "2 frames" in failure and "1 fewer than" in failure


def test_a_duplicated_frame_is_reported():
    passed, failure = JobValidator._compare_frame_hashes(["a", "b"], ["a", "a", "b"])

    assert passed is False
    assert "more than" in failure


def test_the_first_differing_frame_is_named():
    """
    The frame number points straight at the split that went wrong.

    "Something differs" would leave you bisecting a hundred shots by hand.
    """
    passed, failure = JobValidator._compare_frame_hashes(["a", "b", "c"], ["a", "x", "c"])

    assert passed is False
    assert "Frame 1 differs" in failure


# --- ROUND TRIP (needs ffmpeg) ---


@pytest.fixture
def split_job(toolchain, clips, tmp_path):
    """A real mezzanine split into three shots, ready to be rejoined."""
    probed = SourceProbe(toolchain).probe(clips["pal"])
    mezzanine = MezzanineBuilder(toolchain).build(probed, tmp_path / "mezz.mov")
    splitter = ShotSplitter(toolchain, mezzanine, probed, tmp_path / "shots")

    shots = splitter.extract_all([
        Shot(index=1, start_frame=0, end_frame=19),
        Shot(index=2, start_frame=20, end_frame=34),
        Shot(index=3, start_frame=35, end_frame=49),
    ])

    return probed, mezzanine, shots


def test_a_correct_split_survives_the_round_trip(toolchain, split_job, tmp_path):
    """
    Rejoining the shots gives back the mezzanine, frame for frame.

    This is the strongest check in the project: it proves the pixels, where
    every other check only proves the numbers.
    """
    probed, mezzanine, shots = split_job

    passed, failure = JobValidator(toolchain).verify_round_trip(
        mezzanine, shots, tmp_path / "work"
    )

    assert passed is True, failure


def test_a_dropped_shot_fails_the_round_trip(toolchain, split_job, tmp_path):
    """Losing a shot is caught even though the remaining files are all valid."""
    probed, mezzanine, shots = split_job

    passed, failure = JobValidator(toolchain).verify_round_trip(
        mezzanine, shots[:2], tmp_path / "work"
    )

    assert passed is False
    assert "fewer than" in failure


def test_shots_in_the_wrong_order_fail_the_round_trip(toolchain, split_job, tmp_path):
    """
    Reordering keeps every frame but ruins every clip.

    The frame count still matches, so only a pixel comparison can catch it.
    """
    probed, mezzanine, shots = split_job
    swapped = [shots[1], shots[0], shots[2]]
    for index, shot in enumerate(swapped, start=1):
        shot.index = index

    passed, failure = JobValidator(toolchain).verify_round_trip(
        mezzanine, swapped, tmp_path / "work"
    )

    assert passed is False
    assert "differs" in failure


def test_the_work_directory_is_left_clean(toolchain, split_job, tmp_path):
    """Scratch files are removed whether the check passed or failed."""
    probed, mezzanine, shots = split_job
    work_dir = tmp_path / "work"

    JobValidator(toolchain).verify_round_trip(mezzanine, shots, work_dir)

    assert list(work_dir.iterdir()) == []


def test_a_shot_with_no_file_is_refused(toolchain, tmp_path):
    """Rejoining shots that were never written is a bug, not a failed check."""
    with pytest.raises(ValueError, match="no file"):
        JobValidator(toolchain)._build_concat_list(
            [Shot(index=1, start_frame=0, end_frame=9)], tmp_path / "concat.txt"
        )


# --- BOUNDARY FRAMES (the default pixel check) ---


def test_a_correct_split_passes_the_boundary_check(toolchain, split_job):
    probed, mezzanine, shots = split_job

    passed, failure = JobValidator(toolchain).verify_boundary_frames(mezzanine, shots, probed)

    assert passed is True, failure


def test_boundary_check_catches_a_shot_cut_from_the_wrong_place(toolchain, split_job, tmp_path):
    """
    A shot of the right length taken from the wrong frames is the failure this
    exists to catch, and the one no frame count can see.
    """
    probed, mezzanine, shots = split_job

    # Same length as shot 2, but lifted from five frames earlier
    wrong = ShotSplitter(toolchain, mezzanine, probed, tmp_path / "wrong").extract(
        Shot(index=2, start_frame=15, end_frame=29)
    )
    shots[1].file = str(wrong)

    passed, failure = JobValidator(toolchain).verify_boundary_frames(mezzanine, shots, probed)

    assert passed is False
    assert "shot 2" in failure


def test_boundary_check_catches_shots_holding_the_wrong_content(toolchain, split_job):
    """
    Two shots whose files are swapped: each claims a frame range its file does
    not contain.

    This is what "shots in the wrong order" means in practice — the frame
    counts are all correct and every file is valid, so nothing but a pixel
    comparison notices.
    """
    probed, mezzanine, shots = split_job
    shots[0].file, shots[1].file = shots[1].file, shots[0].file

    passed, failure = JobValidator(toolchain).verify_boundary_frames(mezzanine, shots, probed)

    assert passed is False
    assert "shot 1" in failure


def test_boundary_check_is_much_cheaper_than_the_round_trip(toolchain, split_job, tmp_path):
    """
    Both checks agree on a correct job; the boundary check just does far less
    work. This asserts the agreement — the speed difference is measured in
    the notes on `verify_boundary_frames`, not here, because timings in a test
    suite are flaky.
    """
    probed, mezzanine, shots = split_job
    validator = JobValidator(toolchain)

    boundary_passed, _ = validator.verify_boundary_frames(mezzanine, shots, probed)
    round_trip_passed, _ = validator.verify_round_trip(mezzanine, shots, tmp_path / "work")

    assert boundary_passed == round_trip_passed is True


def test_boundary_check_refuses_a_shot_with_no_file(toolchain, split_job):
    probed, mezzanine, shots = split_job
    shots[0].file = None

    with pytest.raises(ValueError, match="no file"):
        JobValidator(toolchain).verify_boundary_frames(mezzanine, shots, probed)


# --- FULL JOB VALIDATION ---


def test_validate_job_checks_boundaries_by_default(toolchain, split_job, tmp_path):
    """The default is the cheap pixel check, and the sidecar records which ran."""
    probed, mezzanine, shots = split_job

    result = JobValidator(toolchain).validate_job(shots, probed, mezzanine, tmp_path / "work")

    assert result.passed is True
    assert result.checks[CHECK_BOUNDARY_FRAMES] is True
    assert CHECK_ROUND_TRIP not in result.checks, "the expensive check was not asked for"


def test_validate_job_runs_the_round_trip_when_asked(toolchain, split_job, tmp_path):
    probed, mezzanine, shots = split_job

    result = JobValidator(toolchain).validate_job(
        shots, probed, mezzanine, tmp_path / "work", full_round_trip=True
    )

    assert result.passed is True
    assert result.checks[CHECK_ROUND_TRIP] is True
    assert CHECK_BOUNDARY_FRAMES not in result.checks


def test_validate_job_skips_the_pixel_check_when_the_numbers_are_wrong(toolchain, split_job, tmp_path):
    """
    The expensive check is not run to confirm a problem already found.

    Its failure would be a consequence of the first one rather than a second
    finding, and would read as two unrelated faults.
    """
    probed, mezzanine, shots = split_job
    short = shots[:2]  # no longer covers the source

    result = JobValidator(toolchain).validate_job(short, probed, mezzanine, tmp_path / "work")

    assert result.passed is False
    assert result.checks[CHECK_BOUNDARY_FRAMES] is False
    assert any("not attempted" in failure for failure in result.failures)
