"""
Frame-Accurate Shot Extraction.

Cuts each shot out of the mezzanine as its own file.

Because the mezzanine is all-intra, these are stream copies: fast, lossless,
and landing exactly on the requested frame. Cutting the original source
directly would silently snap to the nearest keyframe instead.
"""

import logging
from pathlib import Path
from typing import Callable, List, Optional

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo
from src.core.timecode import Timecode

# --- NAMING ---

# Zero-padded so shots sort correctly in every file browser, and stable so the
# identifier tab can rename from this without guessing.
SHOT_FILENAME_TEMPLATE = "shot_{index:03d}{suffix}"


class ShotSplitter:
    """
    Cuts shots out of a mezzanine.

    Holds the mezzanine, the source's timecode and the output directory for the
    whole job, so each call needs only the shot itself.
    """

    def __init__(
        self,
        toolchain: MediaToolchain,
        mezzanine_path: Path,
        source: SourceInfo,
        output_dir: Path,
        suffix: str = ".mov",
    ):
        """
        Args:
            toolchain: Shared ffmpeg toolchain.
            mezzanine_path: The all-intra file to copy from.
            source: Probed source, used for the exact frame rate.
            output_dir: Where shot files are written.
            suffix: Container for the written shots, matching the mezzanine.
        """
        self.toolchain = toolchain
        self.mezzanine_path = mezzanine_path
        self.source = source
        self.output_dir = output_dir
        self.suffix = suffix
        self.timecode = Timecode.from_source(source)

    # --- NAMING ---

    def filename_for(self, shot: Shot) -> str:
        """Returns the output filename for a shot, e.g. 'shot_007.mov'."""
        return SHOT_FILENAME_TEMPLATE.format(index=shot.index, suffix=self.suffix)

    # --- CUTTING ---

    def extract(self, shot: Shot) -> Path:
        """
        Writes a single shot to its own file.

        Args:
            shot: The shot to cut, as an inclusive frame range.

        Returns:
            Path to the written file.

        Raises:
            RuntimeError: If ffmpeg fails, or the written frame count does not
                match shot.frame_count.

        Notes:
            -ss goes BEFORE -i so ffmpeg seeks rather than decoding and
            discarding. Start and duration come from Timecode as exact
            Fractions, never floats, and the duration covers frame_count frames
            — not (end - start), which would drop the last frame.
        """
        # PSEUDOCODE
        # 1. start = timecode.frame_to_seconds(shot.start_frame)
        # 2. duration = timecode.frame_to_seconds(shot.frame_count)
        # 3. run ffmpeg: -ss <start> -i <mezzanine> -t <duration> -c copy <output>
        # 4. Probe the result and assert its frame count equals shot.frame_count.
        raise NotImplementedError

    def extract_all(
        self,
        shots: List[Shot],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Shot]:
        """
        Cuts every shot, recording the written path on each one.

        Args:
            shots: The full shot list.
            progress_callback: Receives (shots_done, shots_total) for the UI.

        Returns:
            The same shots with `file` populated.

        Raises:
            RuntimeError: On the first shot that fails. A partial set of splits
                is worse than none, because the gap is easy to miss.
        """
        # PSEUDOCODE
        # 1. ensure_directory(self.output_dir).
        # 2. For each shot: extract(), set shot.file, report progress.
        # 3. Return the updated list.
        raise NotImplementedError
