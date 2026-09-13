"""
PySceneDetect Passes.

Two detectors, both from PySceneDetect, neither of them a neural network. Each
compares a frame with the one before it — a colour histogram difference — and
decides whether the change is large enough to be a cut.

**ContentDetector** compares that difference against a fixed threshold.

**AdaptiveDetector** compares it against a rolling average of the surrounding
frames instead, so a cut has to stand out from its neighbours rather than from
a constant.

Both run, because measuring them on real deliveries showed they fail in
opposite directions:

- On a photoreal night sequence of people running, every boundary Content found
  alone was a real cut. Adaptive missed all six, because when the whole clip is
  high-motion the rolling baseline is already high and a genuine cut does not
  stand out by ratio.
- On Unreal previz, four of five Content-only boundaries were near-identical
  frames — false positives — while Adaptive found two real cuts Content missed.

So neither dominates, and the union of the two is what gets used. That trade
favours recall deliberately: a person reviews every boundary before anything is
written, and a false positive is a visible tick to delete, while a miss is
invisible unless they watch the whole thing.
"""

import logging
from pathlib import Path
from typing import List, Optional

from src.core.models import Boundary

# --- DETECTOR NAMES ---

# Recorded on every boundary and written into the sidecar, so a job says which
# detectors agreed rather than only that something found a cut.
CONTENT = "content"
ADAPTIVE = "adaptive"

# PySceneDetect's own defaults. They are not tuned here: tuning without ground
# truth is tuning by eye, which CLAUDE.md rules out.
CONTENT_THRESHOLD = 27.0
ADAPTIVE_THRESHOLD = 3.0

# Below this, PySceneDetect will not report a new scene at all. Deliberately
# small: merging genuinely short shots is a decision for reconciliation, with
# the merge recorded, rather than something a detector does quietly.
MINIMUM_SCENE_FRAMES = 5


class SceneDetectPass:
    """
    One PySceneDetect detector, run over a source.

    Holds only its own settings — the video is opened per call, since nothing
    survives between them.

    Exposes the same `detect()` signature as every other pass, so
    reconciliation does not care which one produced a boundary.
    """

    def __init__(self, kind: str = CONTENT, threshold: Optional[float] = None):
        """
        Args:
            kind: CONTENT or ADAPTIVE.
            threshold: Overrides the detector's default. Left alone unless
                there is ground truth to justify a change.

        Raises:
            ValueError: If `kind` is not one of the two.
        """
        if kind not in (CONTENT, ADAPTIVE):
            raise ValueError(f"Unknown detector {kind!r}; expected {CONTENT} or {ADAPTIVE}")

        self.kind = kind
        self.threshold = threshold

    # --- DETECTION ---

    def _build_detector(self):
        """
        Builds the PySceneDetect detector for this pass.

        Imported here rather than at module level because PySceneDetect pulls
        in OpenCV, which is slow to load and not needed to probe or cut.
        """
        from scenedetect.detectors import AdaptiveDetector, ContentDetector

        if self.kind == ADAPTIVE:
            return AdaptiveDetector(
                adaptive_threshold=self.threshold or ADAPTIVE_THRESHOLD,
                min_scene_len=MINIMUM_SCENE_FRAMES,
            )

        return ContentDetector(
            threshold=self.threshold or CONTENT_THRESHOLD,
            min_scene_len=MINIMUM_SCENE_FRAMES,
        )

    def detect(self, source_path: Path) -> List[Boundary]:
        """
        Finds shot boundaries in a source.

        Args:
            source_path: The mini cut, or the mezzanine cut from it — both give
                the same frame numbers, since the mezzanine is verified frame
                for frame against its source.

        Returns:
            Boundaries with this detector's name recorded, sorted by frame.

        Notes:
            PySceneDetect reports scenes as start and end pairs in its own
            FrameTimecode type. We take the start of every scene after the
            first — the first scene starts at frame 0, which is not a cut — and
            convert to plain integers here, so its timecode objects never leak
            into the rest of the project.
        """
        from scenedetect import SceneManager, open_video

        # PySceneDetect narrates its own progress at INFO, which would bury the
        # app's log in "Detecting scenes..." on every job
        logging.getLogger("pyscenedetect").setLevel(logging.WARNING)

        video = open_video(str(source_path))
        manager = SceneManager()
        manager.add_detector(self._build_detector())
        manager.detect_scenes(video, show_progress=False)

        scenes = manager.get_scene_list()
        boundaries = [
            Boundary(frame=int(start.frame_num), found_by=[self.kind])
            for start, _ in scenes[1:]
        ]

        logging.info(f"{self.kind} found {len(boundaries)} boundaries in {source_path.name}")
        return boundaries


def detect_all(source_path: Path) -> List[List[Boundary]]:
    """
    Runs every pass over a source.

    Returns:
        One boundary list per detector, for reconciliation to merge. Kept
        separate rather than combined here so the merge can tell which
        detectors agreed on what.
    """
    return [SceneDetectPass(kind).detect(source_path) for kind in (CONTENT, ADAPTIVE)]
