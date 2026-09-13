"""
Tests for the Shot List Integrity Checks.

Pure arithmetic, so these need no ffmpeg, no fixture clips and no temporary
files — which is the point of the module they cover. The cases are
deliberately the broken lists: one that sums wrong, has a hole in it,
double-counts a frame, or stops short of the end.
"""

from src.core.models import Shot, SourceInfo
from src.splitter.integrity import (
    CHECK_BOUNDS,
    CHECK_FRAMES_SUM,
    CHECK_NO_GAPS,
    CHECK_NO_OVERLAPS,
    validate_shot_list,
)

# --- HELPERS ---

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
    result = validate_shot_list(shots((0, 49), (50, 99)), source(100))

    assert result.passed is True
    assert result.failures == []
    assert all(result.checks.values())


def test_a_single_shot_covering_everything_passes():
    result = validate_shot_list(shots((0, 99)), source(100))

    assert result.passed is True


# --- FRAME TOTALS ---


def test_frames_must_sum_to_the_source():
    """One frame short is still wrong — there is no tolerance here."""
    result = validate_shot_list(shots((0, 49), (50, 98)), source(100))

    assert result.passed is False
    assert result.checks[CHECK_FRAMES_SUM] is False
    assert "99 frames" in result.failures[0]


# --- GAPS ---


def test_a_gap_is_caught_and_located():
    """Frames in a gap belong to no shot, so they would never be written."""
    result = validate_shot_list(shots((0, 49), (60, 99)), source(100))

    assert result.passed is False
    assert result.checks[CHECK_NO_GAPS] is False

    gap = next(failure for failure in result.failures if "Gap" in failure)
    assert "10 frames" in gap
    assert "ends 49" in gap and "starts 60" in gap


# --- OVERLAPS ---


def test_an_overlap_is_caught_and_located():
    """An overlapping frame gets written into two shots."""
    result = validate_shot_list(shots((0, 50), (50, 99)), source(100))

    assert result.passed is False
    assert result.checks[CHECK_NO_OVERLAPS] is False

    overlap = next(failure for failure in result.failures if "share" in failure)
    assert "share 1 frame" in overlap


def test_a_larger_overlap_reports_its_size():
    result = validate_shot_list(shots((0, 59), (50, 99)), source(100))

    overlap = next(failure for failure in result.failures if "share" in failure)
    assert "share 10 frames" in overlap


# --- BOUNDS ---


def test_a_list_that_does_not_start_at_zero_fails():
    """The head of the source would belong to no shot."""
    result = validate_shot_list(shots((10, 99)), source(100))

    assert result.checks[CHECK_BOUNDS] is False
    assert any("starts at frame 10" in failure for failure in result.failures)


def test_a_list_that_stops_short_of_the_end_fails():
    """The tail of the source would be silently dropped."""
    result = validate_shot_list(shots((0, 89)), source(100))

    assert result.checks[CHECK_BOUNDS] is False
    assert any("ends at frame 89" in failure for failure in result.failures)


def test_an_inside_out_shot_fails():
    """A shot ending before it starts cannot be cut at all."""
    result = validate_shot_list(
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
    result = validate_shot_list([], source(100))

    assert result.passed is False
    assert result.failures
    assert not any(result.checks.values())


# --- REPORTING ---


def test_every_check_is_recorded_by_name():
    """The sidecar records which checks ran, not just whether the job passed."""
    result = validate_shot_list(shots((0, 99)), source(100))

    assert set(result.checks) == {
        CHECK_FRAMES_SUM,
        CHECK_NO_GAPS,
        CHECK_NO_OVERLAPS,
        CHECK_BOUNDS,
    }


def test_several_problems_are_all_reported():
    """One run names everything wrong, rather than stopping at the first."""
    result = validate_shot_list(shots((5, 49), (60, 90)), source(100))

    assert len(result.failures) >= 3, result.failures


def test_shots_are_checked_in_frame_order_not_list_order():
    """A correct list that arrives out of order is still correct."""
    out_of_order = [
        Shot(index=2, start_frame=50, end_frame=99),
        Shot(index=1, start_frame=0, end_frame=49),
    ]

    assert validate_shot_list(out_of_order, source(100)).passed is True


