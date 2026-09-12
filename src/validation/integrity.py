"""
Shot List Integrity Checks.

Plain arithmetic on a shot list: the durations sum to the source, there are no
gaps, no overlaps, and the list starts and ends where the source does.

This catches the whole class of off-by-one bugs. A shot list whose frames do
not add up is wrong however good the detection was, and saying so costs
nothing — which is why it runs before any transcoding rather than after.

Functions rather than a class, and no toolchain: these checks touch no files,
run no subprocesses and hold nothing between calls. Everything that needs
ffmpeg lives in `validator.py` alongside them.
"""

import logging
from typing import List

from src.core.models import Shot, SourceInfo, ValidationResult

# --- CHECK NAMES ---

# Stable keys, recorded in the sidecar's validation block.
CHECK_FRAMES_SUM = "frames_sum"
CHECK_NO_GAPS = "no_gaps"
CHECK_NO_OVERLAPS = "no_overlaps"
CHECK_BOUNDS = "bounds"

INTEGRITY_CHECKS = (CHECK_FRAMES_SUM, CHECK_NO_GAPS, CHECK_NO_OVERLAPS, CHECK_BOUNDS)


# --- PUBLIC API ---


def validate_shot_list(shots: List[Shot], source: SourceInfo) -> ValidationResult:
    """
    Runs every arithmetic check on a shot list.

    Called twice in a job: once as soon as the boundaries are known, so a broken
    list stops the job before an hour of transcoding, and once on the shots as
    they were actually written.

    Args:
        shots: The shot list, in any order — it is sorted by start frame here.
        source: The probed source, for its frame count.

    Returns:
        ValidationResult with one entry per check. `passed` is False if any
        check failed, and every problem is described rather than just the first.
    """
    if not shots:
        # Every "walk the adjacent pairs" check is trivially true with nothing
        # to walk, so an empty list would otherwise report a clean pass on a
        # job that produced no shots at all
        return ValidationResult(
            passed=False,
            checks={name: False for name in INTEGRITY_CHECKS},
            failures=["The shot list is empty, so there is nothing to cut"],
        )

    ordered = sorted(shots, key=lambda shot: shot.start_frame)

    results = {
        CHECK_FRAMES_SUM: _check_frames_sum(ordered, source.frame_count),
        CHECK_NO_GAPS: _check_no_gaps(ordered),
        CHECK_NO_OVERLAPS: _check_no_overlaps(ordered),
        CHECK_BOUNDS: _check_bounds(ordered, source.frame_count),
    }

    failures = [failure for problems in results.values() for failure in problems]

    for name, problems in results.items():
        if problems:
            logging.error(f"Validation check {name} failed: {'; '.join(problems)}")

    return ValidationResult(
        passed=not failures,
        checks={name: not problems for name, problems in results.items()},
        failures=failures,
    )


# --- INDIVIDUAL CHECKS ---


def _check_frames_sum(shots: List[Shot], frame_count: int) -> List[str]:
    """
    Every source frame belongs to exactly one shot.

    Compared exactly, with no tolerance: a shot list one frame short is a shot
    list that is wrong somewhere.
    """
    total = sum(shot.frame_count for shot in shots)
    if total == frame_count:
        return []

    difference = total - frame_count
    direction = "more than" if difference > 0 else "fewer than"
    return [
        f"Shots total {total} frames, {abs(difference)} {direction} "
        f"the source's {frame_count}"
    ]


def _check_no_gaps(shots: List[Shot]) -> List[str]:
    """
    Each shot starts on the frame immediately after the previous one ends.

    A gap means frames of the source belong to no shot at all, so they would
    simply never be written.
    """
    problems = []
    for current, following in zip(shots, shots[1:]):
        expected = current.end_frame + 1
        if following.start_frame > expected:
            missing = following.start_frame - expected
            problems.append(
                f"Gap of {missing} frame{'s' if missing > 1 else ''} between "
                f"shot {current.index} (ends {current.end_frame}) and "
                f"shot {following.index} (starts {following.start_frame})"
            )
    return problems


def _check_no_overlaps(shots: List[Shot]) -> List[str]:
    """
    No frame appears in two shots.

    An overlap means a frame is written twice, which the pixel checks would
    also catch — but naming the two shots here is far more useful than a hash
    mismatch later.
    """
    problems = []
    for current, following in zip(shots, shots[1:]):
        if following.start_frame <= current.end_frame:
            shared = current.end_frame - following.start_frame + 1
            problems.append(
                f"Shot {current.index} (ends {current.end_frame}) and "
                f"shot {following.index} (starts {following.start_frame}) "
                f"share {shared} frame{'s' if shared > 1 else ''}"
            )
    return problems


def _check_bounds(shots: List[Shot], frame_count: int) -> List[str]:
    """The shot list covers the source exactly, and no shot is inside out."""
    problems = []

    if shots[0].start_frame != 0:
        problems.append(
            f"First shot starts at frame {shots[0].start_frame}, not 0, "
            f"so the head of the source belongs to no shot"
        )

    last_frame = frame_count - 1
    if shots[-1].end_frame != last_frame:
        problems.append(
            f"Last shot ends at frame {shots[-1].end_frame}, not {last_frame}, "
            f"so the tail of the source is unaccounted for"
        )

    for shot in shots:
        if shot.end_frame < shot.start_frame:
            problems.append(
                f"Shot {shot.index} ends at frame {shot.end_frame}, "
                f"before it starts at {shot.start_frame}"
            )

    return problems
