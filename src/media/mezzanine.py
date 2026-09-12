"""
All-Intra Mezzanine Creation.

Transcodes the source once into a format where every frame is a keyframe.

Why this exists: `ffmpeg -c copy` can only cut on a keyframe. On a long-GOP
source that moves a boundary by up to half a second, silently, with no error.
Making every frame a keyframe first means each split can be a fast stream copy
that lands exactly where it was asked to.

The cost is disk and one slow pass at the start of the job. That trade is
settled — see CLAUDE.md.
"""

import logging
from pathlib import Path
from typing import Callable, Optional

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import SourceInfo

# --- ENCODER SETTINGS ---

# ProRes 422 is the default; DNxHR HQ is the fallback for builds without
# prores_ks. Both are all-intra and visually lossless at these settings.
ENCODER_ARGUMENTS = {
    "prores_ks": ["-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0"],
    "dnxhd": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hq"],
}


class MezzanineBuilder:
    """
    Builds and verifies the all-intra intermediate every split is cut from.

    Holds the toolchain, the chosen encoder and the progress callback for the
    length of a job.
    """

    def __init__(
        self,
        toolchain: MediaToolchain,
        encoder: str = "prores_ks",
        progress_callback: Optional[Callable[[int], None]] = None,
    ):
        """
        Args:
            toolchain: Shared ffmpeg toolchain.
            encoder: Key into ENCODER_ARGUMENTS. Verified against this ffmpeg
                build before a job starts, not here.
            progress_callback: Receives frames completed, for the SSE feed.
        """
        self.toolchain = toolchain
        self.encoder = encoder
        self.progress_callback = progress_callback

    # --- TRANSCODE ---

    def build(self, source: SourceInfo, output_path: Path, crop: Optional[str] = None) -> Path:
        """
        Writes an all-intra copy of the source.

        Args:
            source: Probed source information.
            output_path: Where the mezzanine is written.
            crop: Optional "w:h:x:y" mask to bake in.

        Returns:
            Path to the mezzanine.

        Raises:
            RuntimeError: If ffmpeg fails, or if the output frame count does not
                match the source. A mezzanine one frame short would shift every
                shot after it.
        """
        # PSEUDOCODE
        # 1. Build the command: -i <source> [-vf crop=...] <ENCODER_ARGUMENTS>
        #    -an (audio is handled separately) -progress pipe:1 <output>
        # 2. Run with Popen and read the -progress stream line by line.
        # 3. Parse frame=N lines and hand them to progress_callback.
        # 4. On exit, verify() the result before returning.
        raise NotImplementedError

    def verify(self, source: SourceInfo, mezzanine_path: Path) -> bool:
        """
        Confirms the mezzanine is a frame-for-frame match of the source.

        Checks frame count, resolution after any crop, and frame rate. Called
        before any cutting happens, because everything downstream assumes frame
        N of the mezzanine is frame N of the source.

        Returns:
            True when it matches. Logs precisely which field differs when not.
        """
        # PSEUDOCODE
        # 1. Probe the mezzanine.
        # 2. Compare frame_count, fps rational and dimensions against `source`.
        # 3. Log the differing field before returning False.
        raise NotImplementedError
