"""
All-Intra Mezzanine Creation.

Re-encodes the source once into the same codec it arrived in, but with every
frame a keyframe.

Why this exists: in h264 and h265 most frames are defined as differences from
their neighbours, so a file can only start on a keyframe. `ffmpeg -c copy`
therefore snaps a cut to the nearest one, silently moving a boundary by up to
several seconds. Making every frame a keyframe first means each shot can be a
fast stream copy that lands exactly where it was asked to — verified: cutting
30 frames out of an all-intra mezzanine yields 30 frames, pixel-identical.

That costs one re-encode generation, which is unavoidable for frame-accurate
cutting and is why the quality setting is deliberately transparent.

The mezzanine is always full frame and always the source's own codec. Detected
letterboxing is information about the source, not an instruction to reshape it:
a splitter's output must be the source's own shots, bars and all.
"""

from pathlib import Path
from typing import List

from src.core.config import MEZZANINE_CRF, MEZZANINE_ENCODERS, MEZZANINE_PRESET
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import SourceInfo

# --- ENCODER SETTINGS ---

# Every frame a keyframe. x264 takes -g 1; x265 wants it through -x265-params.
INTRA_ARGUMENTS = {
    "libx264": ["-g", "1"],
    "libx265": ["-x265-params", "keyint=1"],
}


class MezzanineBuilder:
    """
    Builds and verifies the all-intra intermediate every shot is cut from.

    The encoder is not configurable: it follows the source codec, because shots
    come out in the format they went in as.
    """

    def __init__(self, toolchain: MediaToolchain):
        self.toolchain = toolchain

    # --- ENCODER SELECTION ---

    @staticmethod
    def encoder_for(source: SourceInfo) -> str:
        """
        The encoder that writes an all-intra version of this source.

        Raises:
            ValueError: If the source codec is not one we can reproduce. Better
                to say so than to hand back shots in a different format from the
                ones that went in.
        """
        encoder = MEZZANINE_ENCODERS.get(source.codec)
        if encoder is None:
            supported = ", ".join(sorted(MEZZANINE_ENCODERS))
            raise ValueError(f"Cannot re-encode {source.codec!r}; supported codecs are {supported}")
        return encoder

    def arguments_for(self, source: SourceInfo) -> List[str]:
        """
        The encoding arguments for a source.

        Pixel format is carried across explicitly so a 10-bit source is not
        quietly flattened to 8-bit on the way out.
        """
        encoder = self.encoder_for(source)

        return [
            "-c:v", encoder,
            "-preset", MEZZANINE_PRESET,
            "-crf", str(MEZZANINE_CRF),
            *INTRA_ARGUMENTS[encoder],
            "-pix_fmt", source.pixel_format,
        ]

    # --- TRANSCODE ---

    def build(self, source: SourceInfo, output_path: Path) -> Path:
        """
        Writes an all-intra copy of the source, at full frame.

        Args:
            source: Probed source information.
            output_path: Where the mezzanine is written. Its extension should
                match the source container, so the shots cut from it do too.

        Returns:
            Path to the mezzanine.

        Raises:
            ValueError: If the source codec cannot be reproduced.
            RuntimeError: If ffmpeg fails, or the output frame count does not
                match the source. A mezzanine one frame short would shift every
                shot after it.
        """
        # PSEUDOCODE
        # 1. Build the command: -i <source> arguments_for(source)
        #    -an (audio is handled separately) <output>
        # 2. Run it with a generous timeout — this is the slow pass of the job.
        # 3. Raise on a non-zero exit, with ffmpeg's own stderr attached.
        # 4. verify() the result before returning it.
        raise NotImplementedError

    def verify(self, source: SourceInfo, mezzanine_path: Path) -> bool:
        """
        Confirms the mezzanine is a frame-for-frame match of the source.

        Checks frame count, resolution and frame rate. Called before any cutting
        happens, because everything downstream assumes frame N of the mezzanine
        is frame N of the source.

        Returns:
            True when it matches. Logs precisely which field differs when not.
        """
        # PSEUDOCODE
        # 1. Probe the mezzanine.
        # 2. Compare frame_count, fps rational and dimensions against `source`.
        # 3. Log the differing field before returning False.
        raise NotImplementedError
