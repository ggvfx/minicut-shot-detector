"""
Tests for Turning Boundaries Into Shots.

This is the single subtraction where an off-by-one would put a frame of the
next shot on the end of this one, so the cases here are mostly about the edges:
the first shot, the last shot, and the frame either side of a cut.
"""

import pytest

from src.core.models import Boundary
from src.splitter.reconcile import boundaries_to_shots
from src.splitter.scene_detect import ADAPTIVE, CONTENT

# --- HELPERS ---


def at(frame: int, confidence: float = 1.0, agreed: bool = True) -> Boundary:
    """
    A boundary at a frame, with both detectors agreeing by default.

    Agreement is expressed as the list of detectors that found it, because that
    is what `Boundary` holds. This helper used to pass `found_by_transnet` and
    `found_by_scenedetect`, which stopped existing when found_by became a list
    — and Pydantic drops unknown fields silently, so every boundary it built
    came out with found_by=[] and the assertions below passed by accident.
    """
    return Boundary(
        frame=frame,
        confidence=confidence,
        found_by=[CONTENT, ADAPTIVE] if agreed else [CONTENT],
    )


# --- BASIC SHAPE ---


def test_no_boundaries_gives_one_shot():
    """A source with no cuts is one shot covering everything."""
    shots = boundaries_to_shots([], frame_count=100)

    assert len(shots) == 1
    assert (shots[0].start_frame, shots[0].end_frame) == (0, 99)
    assert shots[0].frame_count == 100


def test_one_boundary_gives_two_shots():
    """
    A cut at frame 50 means shot one ends at 49 — not 50.

    Getting this wrong puts the first frame of the new shot on the tail of the
    old one, which looks like a one frame flash at the end of every clip.
    """
    shots = boundaries_to_shots([at(50)], frame_count=100)

    assert len(shots) == 2
    assert (shots[0].start_frame, shots[0].end_frame) == (0, 49)
    assert (shots[1].start_frame, shots[1].end_frame) == (50, 99)


def test_shots_are_numbered_from_one():
    shots = boundaries_to_shots([at(10), at(20)], frame_count=30)

    assert [shot.index for shot in shots] == [1, 2, 3]


def test_shots_tile_the_source_exactly():
    """Every frame belongs to exactly one shot, with nothing left over."""
    shots = boundaries_to_shots([at(17), at(43), at(88)], frame_count=120)

    assert sum(shot.frame_count for shot in shots) == 120
    assert shots[0].start_frame == 0
    assert shots[-1].end_frame == 119

    for current, following in zip(shots, shots[1:]):
        assert following.start_frame == current.end_frame + 1


# --- EDGES ---


def test_boundary_on_the_last_frame():
    """A cut on the final frame makes a legitimate one frame shot."""
    shots = boundaries_to_shots([at(99)], frame_count=100)

    assert (shots[-1].start_frame, shots[-1].end_frame) == (99, 99)
    assert shots[-1].frame_count == 1


def test_boundary_at_frame_zero_is_dropped():
    """
    The first shot already starts at frame 0, so a boundary there adds nothing.

    Keeping it would open a shot containing no frames.
    """
    shots = boundaries_to_shots([at(0), at(50)], frame_count=100)

    assert len(shots) == 2
    assert (shots[0].start_frame, shots[0].end_frame) == (0, 49)


def test_single_frame_source():
    shots = boundaries_to_shots([], frame_count=1)

    assert len(shots) == 1
    assert (shots[0].start_frame, shots[0].end_frame) == (0, 0)


def test_unsorted_boundaries_are_ordered():
    """Boundaries can be typed by hand, so their order is not assumed."""
    shots = boundaries_to_shots([at(80), at(20), at(50)], frame_count=100)

    assert [shot.start_frame for shot in shots] == [0, 20, 50, 80]


# --- CONFIDENCE CARRIED OVER ---


def test_confidence_comes_from_the_boundary_that_opened_the_shot():
    """A shot is as trustworthy as the cut that started it."""
    shots = boundaries_to_shots([at(50, confidence=0.62, agreed=False)], frame_count=100)

    assert shots[1].confidence == pytest.approx(0.62)
    assert shots[1].detectors_agreed is False


def test_an_agreed_boundary_opens_a_shot_that_is_not_flagged():
    """
    Agreement has to survive the conversion, not just disagreement.

    This is the half that decides whether a cut shows as a plain tick or an
    amber one, and it went untested while the helper was silently producing
    boundaries no detector had found.
    """
    shots = boundaries_to_shots([at(50, agreed=True)], frame_count=100)

    assert shots[1].detectors_agreed is True


def test_first_shot_is_not_flagged_for_review():
    """
    The first shot is opened by the start of the file, not by a detection.

    Marking it as a disagreement would send the user to review something no
    detector ever had an opinion about.
    """
    shots = boundaries_to_shots([at(50, confidence=0.5, agreed=False)], frame_count=100)

    assert shots[0].confidence == 1.0
    assert shots[0].detectors_agreed is True


# --- REJECTED INPUT ---


@pytest.mark.parametrize("frame", [100, 101, 500])
def test_boundary_past_the_end_is_rejected(frame):
    """A cut beyond the source would silently produce an unwritable shot."""
    with pytest.raises(ValueError, match="outside the source"):
        boundaries_to_shots([at(frame)], frame_count=100)


def test_negative_boundary_is_rejected():
    with pytest.raises(ValueError, match="outside the source"):
        boundaries_to_shots([at(-5)], frame_count=100)


def test_duplicate_boundaries_are_rejected():
    """
    Two cuts on one frame would open a shot with no frames in it.

    Failing here names the frame; failing later would just produce a zero
    length file.
    """
    with pytest.raises(ValueError, match="share frame 50"):
        boundaries_to_shots([at(50), at(50)], frame_count=100)


@pytest.mark.parametrize("frame_count", [0, -1])
def test_empty_source_is_rejected(frame_count):
    with pytest.raises(ValueError, match="at least one frame"):
        boundaries_to_shots([], frame_count=frame_count)
