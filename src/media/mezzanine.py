"""
All-Intra Mezzanine Creation.

Transcodes the source once into a format where every frame is a keyframe.

Why this exists: `ffmpeg -c copy` can only cut on a keyframe. On a long-GOP
source that moves a boundary by up to half a second, silently, with no error.
Making every frame a keyframe first means each split can be a fast stream copy
that lands exactly where it was asked to.

The cost is disk and one slow pass at the start of the job. That trade is
settled — see CLAUDE.md.

The mezzanine is always full frame. Detected letterboxing is information about
the source, not an instruction to reshape it: a splitter's output must be the
source's own shots, bars and all.
"""

import logging
from pathlib import Path
from typing import Optional

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

    Holds the toolchain and the chosen encoder for the length of a job.
    """

    def __init__(self, toolchain: MediaToolchain, encoder: str = "prores_ks"):
        """
        Args:
            toolchain: Shared ffmpeg toolchain.
            encoder: Key into ENCODER_ARGUMENTS. Verified against this ffmpeg
                build before a job starts, not here.
        """
        self.toolchain = toolchain
        self.encoder = encoder

    # --- TRANSCODE ---

    def build(self, source: SourceInfo, output_path: Path) -> Path:
        """
        Writes an all-intra copy of the source, at full frame.

        Args:
            source: Probed source information.
            output_path: Where the mezzanine is written.

        Returns:
            Path to the mezzanine.

        Raises:
            RuntimeError: If ffmpeg fails, or if the output frame count does not
                match the source. A mezzanine one frame short would shift every
                shot after it.

        Notes:
            No crop filter. Baking a detected mask in here would hand the user
            shots that are not the shots they gave us — and cropdetect is
            approximate, reporting heights a couple of pixels apart on files
            from the same delivery.
        """
        # PSEUDOCODE
        # 1. Build the command: -i <source> <ENCODER_ARGUMENTS>
        #    -an (audio is handled separately) <output>
        # 2. Run it, allowing plenty of time — this is the slow pass of the job.
        # 3. On exit, verify() the result before returning.
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
