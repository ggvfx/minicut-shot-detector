"""
PySceneDetect Cross-Check (Secondary Pass).

An independent second opinion using PySceneDetect's AdaptiveDetector, which
compares neighbouring frames statistically and has no idea what a shot is.

It is not here to improve accuracy — TransNetV2 alone would likely be enough
for hard cuts. It is here so the two passes can disagree, because a
disagreement is what flags a boundary for human review, and that flag is what
makes an unattended run safe to trust.
"""

import logging
from pathlib import Path
from typing import List, Optional

from src.core.models import Boundary


class SceneDetectCrossCheck:
    """
    The secondary detector.

    Exposes the same `detect()` signature as TransNetDetector, so reconciliation
    does not care which detector produced which boundary.
    """

    def __init__(self, adaptive_threshold: float = 3.0, min_scene_length: int = 15):
        """
        Args:
            adaptive_threshold: AdaptiveDetector sensitivity. Lower fires more
                readily. The default is PySceneDetect's own.
            min_scene_length: Frames below which PySceneDetect will not report a
                new scene. Our own minimum shot length is applied later, during
                reconciliation — this only stops it reporting noise.
        """
        self.adaptive_threshold = adaptive_threshold
        self.min_scene_length = min_scene_length

    # --- DETECTION ---

    def detect(self, source_path: Path, crop: Optional[str] = None) -> List[Boundary]:
        """
        Runs the AdaptiveDetector pass over the source.

        Args:
            source_path: The mini cut.
            crop: Optional "w:h:x:y" mask, so black bars do not dampen the
                frame-to-frame difference score.

        Returns:
            Boundaries with found_by_scenedetect set, sorted by frame.

        Notes:
            PySceneDetect reports scene START and END pairs in its own
            FrameTimecode type. We take the start of each scene after the first
            and convert to a plain integer frame immediately — its timecode
            objects must not leak into the rest of the project.
        """
        # PSEUDOCODE
        # 1. open_video(source_path).
        # 2. Build a SceneManager, add AdaptiveDetector with our settings.
        # 3. Detect, then collect the scene list.
        # 4. For every scene after the first, take scene_start.get_frames().
        # 5. Wrap each in a Boundary with found_by_scenedetect=True.
        raise NotImplementedError
