"""
Boundary Reconciliation.

Merges the two detector outputs into the single boundary list the cutter works
from, then turns those boundaries into shots.

This is where confidence is decided:
- Both detectors fired    -> high confidence, no review needed
- Only one fired          -> kept, but flagged for human review
- Shot shorter than the minimum -> merged into its neighbour, and the merge is
  recorded on the shot rather than silently applied
"""

import logging
from typing import List, Optional

from src.core.models import Boundary, Shot

# --- MATCHING ---

# Two detectors rarely land on the identical frame. Within this many frames
# they are treated as the same cut. Wider than this and genuinely separate
# fast cuts start being collapsed together.
MATCH_TOLERANCE_FRAMES = 2


def merge_detections(transnet: List[Boundary], scenedetect: List[Boundary]) -> List[Boundary]:
    """
    Combines both detector outputs into one list.

    Args:
        transnet: Boundaries from the primary pass.
        scenedetect: Boundaries from the cross-check pass.

    Returns:
        One boundary per real cut, each recording which detectors found it.
        The TransNetV2 frame wins when the two disagree slightly — it is the
        detector that understands shots.
    """
    # PSEUDOCODE
    # 1. Walk the TransNetV2 list; for each, look for a scenedetect boundary
    #    within MATCH_TOLERANCE_FRAMES.
    # 2. On a match, set both found_by_* flags and keep the TransNetV2 frame.
    # 3. Any unmatched boundary from either list is kept with only its own flag.
    # 4. Sort by frame before returning.
    raise NotImplementedError


# --- MINIMUM SHOT LENGTH ---


def apply_minimum_length(boundaries: List[Boundary], min_length: int) -> List[Boundary]:
    """
    Removes boundaries that would create an impossibly short shot.

    This is the flash-frame filter. A camera flash or a single white frame
    reads as two cuts a few frames apart; real edits do not contain six frame
    shots. Dropping the second boundary of such a pair merges the flash back
    into the shot it belongs to.

    Args:
        boundaries: Merged boundary list, sorted by frame.
        min_length: Shortest acceptable shot, in frames.

    Returns:
        Filtered list. Every removal is logged, never silent.
    """
    # PSEUDOCODE
    # 1. Walk pairs of adjacent boundaries.
    # 2. When the gap is below min_length, drop the LOWER confidence one.
    # 3. Log each removal with both frames and the reason.
    raise NotImplementedError


# --- BOUNDARIES TO SHOTS ---


def boundaries_to_shots(boundaries: List[Boundary], frame_count: int) -> List[Shot]:
    """
    Turns cut points into the inclusive frame ranges the cutter uses.

    Args:
        boundaries: Cut points. Sorted here rather than assumed sorted, because
            these can be typed by hand as well as produced by a detector.
        frame_count: Total frames in the source.

    Returns:
        Shots covering every frame exactly once, numbered from 1.

    Raises:
        ValueError: If frame_count is not positive, or a boundary falls outside
            the source, or two boundaries share a frame. Each would produce a
            shot list that cannot be cut, and saying so here names the frame at
            fault rather than leaving it to fail later.

    Notes:
        The first shot starts at frame 0 whether or not a boundary was detected
        there, and the last shot ends at frame_count - 1. Each shot ends on the
        frame BEFORE the next boundary — this single subtraction is where an
        off-by-one would land a frame of the next shot on the end of this one.

        A boundary at frame 0 is redundant rather than wrong: the first shot
        already starts there. It is dropped, not rejected.
    """
    if frame_count <= 0:
        raise ValueError(f"A source must have at least one frame, got {frame_count}")

    ordered = sorted(boundaries, key=lambda boundary: boundary.frame)

    # Frame 0 is where the first shot starts anyway, so a boundary there adds
    # nothing. Keeping it would open a shot with no frames in it.
    ordered = [boundary for boundary in ordered if boundary.frame != 0]

    seen = set()
    for boundary in ordered:
        if not 0 < boundary.frame < frame_count:
            raise ValueError(
                f"Boundary at frame {boundary.frame} is outside the source "
                f"(0-{frame_count - 1})"
            )
        if boundary.frame in seen:
            raise ValueError(f"Two boundaries share frame {boundary.frame}")
        seen.add(boundary.frame)

    # The boundary that opens each shot, so its confidence can be carried over.
    # The first shot is opened by the start of the file, not by a detection.
    openers: List[Optional[Boundary]] = [None, *ordered]
    starts = [0, *(boundary.frame for boundary in ordered)]

    shots = []
    for index, (start, opener) in enumerate(zip(starts, openers), start=1):
        is_last = index == len(starts)
        end = frame_count - 1 if is_last else starts[index] - 1

        shots.append(
            Shot(
                index=index,
                start_frame=start,
                end_frame=end,
                confidence=opener.confidence if opener else 1.0,
                detectors_agreed=opener.detectors_agreed if opener else True,
            )
        )

    logging.info(f"{len(shots)} shots from {len(ordered)} boundaries over {frame_count} frames")
    return shots
