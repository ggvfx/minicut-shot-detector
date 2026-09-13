"""
Frame Sampling.

Pulls a handful of small frames out of a shot for the vision pass to look at.

Worth being plain about why this exists: **no model watches video.** What is
sold as video understanding is frame sampling underneath, local and hosted
alike. So the useful question is not whether we can send a video — it is which
frames to send, and how small.

Small on purpose. Nothing about judging framing needs 1920 pixels, and a few
hundred keeps API calls cheap, local inference quick, and fits CLI tools that
only accept preview-sized images. The splitter already proved this machinery on
the 640px review proxy.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List

from src.core.ffmpeg_tools import MediaToolchain

# --- SAMPLING ---

# Enough to see a shot change hands without paying for frames that say the same
# thing. A starting point to be measured, not a settled number.
SAMPLE_COUNT = 6

# Long edge in pixels.
SAMPLE_WIDTH = 512

# Taken inside the shot rather than at its very ends: the first and last frames
# of a cut often catch a part-completed motion or a residual blend.
EDGE_TRIM_FRACTION = 0.05


class FrameSampler:
    """
    Extracts sample frames from a single-shot file.

    One ffmpeg call per frame, against the source directly — there is no
    mezzanine here. Approximate seeking is fine: this is describing a shot, not
    cutting it, and a frame either side of the intended one describes the same
    picture.
    """

    def __init__(self, toolchain: MediaToolchain):
        self.toolchain = toolchain

    def sample(self, source_path: Path, output_dir: Path, count: int = SAMPLE_COUNT) -> List[Path]:
        """
        Writes sample frames as small images and returns their paths.

        Args:
            source_path: A single-shot video file.
            output_dir: Where the images go — a working folder, not beside the
                shots.
            count: How many frames. One for a still reference image.

        Returns:
            The written image paths, in time order. Order carries the only
            motion information the model gets, so it must never be shuffled.

        Raises:
            RuntimeError: If the file cannot be read or no frame could be
                extracted.
        """
        # PSEUDOCODE
        # 1. Probe for duration; refuse a file with no video stream.
        # 2. Spread `count` offsets across the middle of the shot, trimmed at
        #    both ends by EDGE_TRIM_FRACTION.
        # 3. Write one scaled JPEG per offset, numbered in time order.
        # 4. Return the paths, raising if none were produced.
        raise NotImplementedError

    def thumbnail(self, source_path: Path, output_path: Path) -> Path:
        """
        One representative frame, for the breakdown export.

        Taken from the middle of the shot. A first frame is often a part-made
        camera move or a character entering, and reads as a worse summary of a
        shot than anything from its middle.
        """
        # PSEUDOCODE
        # 1. Seek to the midpoint and write one scaled image.
        # 2. Return the path.
        raise NotImplementedError
