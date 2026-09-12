"""
Tests for the Shot List Integrity Checks.

These are the cheap checks that run before an hour of transcoding, so the cases
here are deliberately the broken ones: a list that sums wrong, has a hole in
it, double-counts a frame, or does not reach the end of the source.
"""

import pytest

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo
from src.media.mezzanine import MezzanineBuilder
from src.media.probe import SourceProbe
from src.media.splitter import ShotSplitter
from src.validation.validator import (
    CHECK_BOUNDS,
    CHECK_FRAMES_SUM,
    CHECK_NO_GAPS,
    CHECK_NO_OVERLAPS,
    CHECK_ROUND_TRIP,
    JobValidator,
)

# --- HELPERS ---

validator = JobValidator(MediaToolchain(discover=False))


def source(frame_count: int = 100) -> SourceInfo:
    return SourceInfo(
        path="reel.mp4",
        width=1920,
        height=1080,
        fps_numerator=24,
        fps_denominator=1,
        frame_count=frame_count,
        codec="h264",
    )


def shots(*ranges) -> list:
    """Builds a shot list from (start, end) pairs, numbered in order."""
    return [
        Shot(index=index, start_frame=start, end_frame=end)
        for index, (start, end) in enumerate(ranges, start=1)
    ]


# --- A CORRECT LIST ---


def test_a_correct_shot_list_passes():
    result = validator.validate_shot_list(shots((0, 49), (50, 99)), source(100))

    assert result.passed is True
    assert result.failures == []
    assert all(result.checks.values())


def test_a_single_shot_covering_everything_passes():
    result = validator.validate_shot_list(shots((0, 99)), source(100))

    assert result.passed is True


# --- FRAME TOTALS ---


def test_frames_must_sum_to_the_source():
    """One frame short is still wrong — there is no tolerance here."""
    result = validator.validate_shot_list(shots((0, 49), (50, 98)), source(100))

    assert result.passed is False
    assert result.checks[CHECK_FRAMES_SUM] is False
    assert "99 frames" in result.failures[0]


# --- GAPS ---


def test_a_gap_is_caught_and_located():
    """Frames in a gap belong to no shot, so they would never be written."""
    result = validator.validate_shot_list(shots((0, 49), (60, 99)), source(100))

    assert result.passed is False
    assert result.checks[CHECK_NO_GAPS] is False

    gap = next(failure for failure in result.failures if "Gap" in failure)
    assert "10 frames" in gap
    assert "ends 49" in gap and "starts 60" in gap


# --- OVERLAPS ---


def test_an_overlap_is_caught_and_located():
    """An overlapping frame gets written into two shots."""
    result = validator.validate_shot_list(shots((0, 50), (50, 99)), source(100))

    assert result.passed is False
    assert result.checks[CHECK_NO_OVERLAPS] is False

    overlap = next(failure for failure in result.failures if "share" in failure)
    assert "share 1 frame" in overlap


def test_a_larger_overlap_reports_its_size():
    result = validator.validate_shot_list(shots((0, 59), (50, 99)), source(100))

    overlap = next(failure for failure in result.failures if "share" in failure)
    assert "share 10 frames" in overlap


# --- BOUNDS ---


def test_a_list_that_does_not_start_at_zero_fails():
    """The head of the source would belong to no shot."""
    result = validator.validate_shot_list(shots((10, 99)), source(100))

    assert result.checks[CHECK_BOUNDS] is False
    assert any("starts at frame 10" in failure for failure in result.failures)


def test_a_list_that_stops_short_of_the_end_fails():
    """The tail of the source would be silently dropped."""
    result = validator.validate_shot_list(shots((0, 89)), source(100))

    assert result.checks[CHECK_BOUNDS] is False
    assert any("ends at frame 89" in failure for failure in result.failures)


def test_an_inside_out_shot_fails():
    """A shot ending before it starts cannot be cut at all."""
    result = validator.validate_shot_list(
        [Shot(index=1, start_frame=0, end_frame=49), Shot(index=2, start_frame=99, end_frame=50)],
        source(100),
    )

    assert result.checks[CHECK_BOUNDS] is False
    assert any("before it starts" in failure for failure in result.failures)


# --- EMPTY ---


def test_an_empty_shot_list_fails_rather_than_passing_vacuously():
    """
    Nothing to check must not read as nothing wrong.

    An empty list would otherwise satisfy every "walk the pairs" check and
    report a clean pass on a job that produced no shots.
    """
    result = validator.validate_shot_list([], source(100))

    assert result.passed is False
    assert result.failures
    assert not any(result.checks.values())


# --- REPORTING ---


def test_every_check_is_recorded_by_name():
    """The sidecar records which checks ran, not just whether the job passed."""
    result = validator.validate_shot_list(shots((0, 99)), source(100))

    assert set(result.checks) == {
        CHECK_FRAMES_SUM,
        CHECK_NO_GAPS,
        CHECK_NO_OVERLAPS,
        CHECK_BOUNDS,
    }


def test_several_problems_are_all_reported():
    """One run names everything wrong, rather than stopping at the first."""
    result = validator.validate_shot_list(shots((5, 49), (60, 90)), source(100))

    assert len(result.failures) >= 3, result.failures


def test_shots_are_checked_in_frame_order_not_list_order():
    """A correct list that arrives out of order is still correct."""
    out_of_order = [
        Shot(index=2, start_frame=50, end_frame=99),
        Shot(index=1, start_frame=0, end_frame=49),
    ]

    assert validator.validate_shot_list(out_of_order, source(100)).passed is True


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


# --- FULL JOB VALIDATION ---


def test_validate_job_runs_both_kinds_of_check(toolchain, split_job, tmp_path):
    probed, mezzanine, shots = split_job

    result = JobValidator(toolchain).validate_job(shots, probed, mezzanine, tmp_path / "work")

    assert result.passed is True
    assert result.checks[CHECK_ROUND_TRIP] is True
    assert len(result.checks) == 5


def test_validate_job_skips_the_round_trip_when_the_numbers_are_wrong(toolchain, split_job, tmp_path):
    """
    The expensive check is not run to confirm a problem already found.

    Its failure would be a consequence of the first one rather than a second
    finding, and would read as two unrelated faults.
    """
    probed, mezzanine, shots = split_job
    short = shots[:2]  # no longer covers the source

    result = JobValidator(toolchain).validate_job(short, probed, mezzanine, tmp_path / "work")

    assert result.passed is False
    assert result.checks[CHECK_ROUND_TRIP] is False
    assert any("not attempted" in failure for failure in result.failures)
