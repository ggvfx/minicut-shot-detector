"""
Boundary Reconciliation.

Merges what the detectors found into the single boundary list the cutter works
from, then turns those boundaries into shots.

This is where confidence is decided:
- More than one detector fired -> agreed, no particular reason to look
- Only one fired               -> kept, and flagged as worth a glance

Note what that is not: a boundary only one detector found is **kept**, not
discarded. Measuring the two passes on real deliveries showed each finding real
cuts the other missed, so taking only what they agree on would lose material.
The union costs a few extra marks to delete, which is the cheaper mistake when
a person reviews every one of them.
"""

import logging
from typing import List, Optional

from src.core.models import Boundary, Shot

# --- MATCHING ---

# Two detectors rarely land on the identical frame. Within this many frames
# they are treated as the same cut. Wider than this and genuinely separate
# fast cuts start being collapsed together.
MATCH_TOLERANCE_FRAMES = 2


def merge_detections(*passes: List[Boundary]) -> List[Boundary]:
    """
    Combines what every detector found into one list.

    Args:
        *passes: One boundary list per detector, in preference order — the
            first pass wins the frame number where two land a frame or two
            apart.

    Returns:
        One boundary per real cut, sorted by frame, each recording every
        detector that found it. `detectors_agreed` then answers whether it is
        worth a human glance.

    Notes:
        Detectors rarely land on the identical frame, so anything within
        MATCH_TOLERANCE_FRAMES of an existing boundary is treated as the same
        cut rather than a second one. Wider than that and genuinely fast cuts
        would start collapsing together.
    """
    merged: List[Boundary] = []

    for boundaries in passes:
        for boundary in sorted(boundaries, key=lambda item: item.frame):
            existing = _nearest(merged, boundary.frame)

            if existing is None:
                merged.append(boundary.model_copy(deep=True))
                continue

            # Same cut, found again: record the detector and keep the frame
            # from whichever pass claimed it first
            for detector in boundary.found_by:
                if detector not in existing.found_by:
                    existing.found_by.append(detector)

            existing.confidence = max(existing.confidence, boundary.confidence)

    merged.sort(key=lambda item: item.frame)

    agreed = sum(1 for boundary in merged if boundary.detectors_agreed)
    logging.info(
        f"{len(merged)} boundaries from {len(passes)} detectors — "
        f"{agreed} agreed, {len(merged) - agreed} found by one"
    )
    return merged


def _nearest(merged: List[Boundary], frame: int) -> Optional[Boundary]:
    """The already-merged boundary this frame belongs to, if there is one."""
    for boundary in merged:
        if abs(boundary.frame - frame) <= MATCH_TOLERANCE_FRAMES:
            return boundary
    return None


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

    # The boundary that opens each shot, so its confidence and agreement can
    # be carried over. The first shot is opened by the start of the file rather
    # than by a detection, so it is never flagged for review.
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
