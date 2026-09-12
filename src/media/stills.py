"""
Per-Shot Still Extraction.

Pulls a small number of representative frames from each shot: head, middle and
tail by default.

Two jobs, one output. Right now they are the QC contact sheet for the splitter
tab — the fastest way for a human to see that boundaries landed correctly. They
are also what the identifier tab will describe later, which is why they are
written per shot with a predictable name rather than as one contact sheet.
"""

import logging
from pathlib import Path
from typing import List

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo
from src.core.timecode import Timecode

# --- NAMING ---

STILL_FILENAME_TEMPLATE = "shot_{index:03d}_{position}.jpg"

# Named rather than numbered so the identifier can ask for "the middle frame"
# without knowing how many stills were taken.
POSITIONS = ("head", "mid", "tail")

# JPEG quality for ffmpeg's -q:v, where 2 is near-lossless. These are looked at
# by humans and fed to a vision model, so artefacts are not worth the disk saved.
JPEG_QUALITY = 2


class StillExtractor:
    """
    Writes representative stills for each shot.

    Separate from ShotSplitter because the identifier tab consumes stills
    independently of the shot files themselves.
    """

    def __init__(self, toolchain: MediaToolchain, source: SourceInfo, output_dir: Path, count: int = 3):
        """
        Args:
            toolchain: Shared ffmpeg toolchain.
            source: Probed source, used for the exact frame rate.
            output_dir: Where stills are written.
            count: Stills per shot. Three gives head, mid and tail.
        """
        self.toolchain = toolchain
        self.source = source
        self.output_dir = output_dir
        self.count = count
        self.timecode = Timecode.from_source(source)

    # --- FRAME SELECTION ---

    def positions_for(self, shot: Shot) -> List[int]:
        """
        Chooses which frames to grab from a shot.

        Args:
            shot: The shot to sample.

        Returns:
            Absolute frame indices within the source.

        Notes:
            Head and tail are pulled one frame inside the boundary. The exact
            first and last frames are the ones most likely to catch a residual
            flash or a part-way-through camera move.
        """
        # PSEUDOCODE
        # 1. If the shot is shorter than `count` frames, return what fits.
        # 2. head = start_frame + 1, tail = end_frame - 1, mid = midpoint.
        # 3. For counts above three, space the extras evenly between.
        raise NotImplementedError

    # --- EXTRACTION ---

    def extract(self, shot: Shot, shot_file: Path) -> List[Path]:
        """
        Writes stills for one shot.

        Args:
            shot: The shot being sampled.
            shot_file: The already-cut shot file, not the mezzanine. Seeking in
                a short file is fast and keeps frame numbers local to the shot.

        Returns:
            Paths to the written stills, in head-to-tail order.
        """
        # PSEUDOCODE
        # 1. ensure_directory(self.output_dir).
        # 2. Convert each absolute frame from positions_for() to an offset
        #    within the shot file (frame - shot.start_frame).
        # 3. For each: ffmpeg -ss <offset seconds> -i <shot_file>
        #    -frames:v 1 -q:v JPEG_QUALITY <output>
        # 4. Return the written paths.
        raise NotImplementedError
