"""
Frame-Accurate Shot Extraction.

Cuts each shot out of the mezzanine as its own file.

Because the mezzanine is all-intra, these are stream copies: fast, lossless,
and landing exactly on the requested frame. Cutting the original source
directly would silently snap to the nearest keyframe instead.
"""

import logging
from pathlib import Path
from typing import List

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo
from src.core.timecode import Timecode
from src.core.utils import ensure_directory
from src.media.probe import SourceProbe

# --- STREAMS ---

# The first video stream and any audio, copied rather than re-encoded. The "?"
# makes audio optional, so a silent source is not an error.
COPY_ARGUMENTS = ["-map", "0:v:0", "-map", "0:a?", "-c", "copy"]

# Cutting is a stream copy and therefore fast, but a long shot on a slow disk
# should still not be abandoned early.
EXTRACT_TIMEOUT = 600.0

# --- NAMING ---

# Named after the mini cut they came from, so splitting two cuts into one
# directory cannot have the second overwrite the first. Zero-padded so shots
# sort correctly in every file browser.
#
# These names are deliberately plain: the identifier tab renames shots from the
# supplied shot list, so padding and increments are not worth making options
# when the result is replaced one step later.
SHOT_FILENAME_TEMPLATE = "{stem}_shot_{index:03d}{suffix}"


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
    ):
        """
        Args:
            toolchain: Shared ffmpeg toolchain.
            mezzanine_path: The all-intra file to copy from.
            source: Probed source, used for the exact frame rate.
            output_dir: Where shot files are written.
        """
        self.toolchain = toolchain
        self.mezzanine_path = mezzanine_path
        self.source = source
        self.output_dir = output_dir
        self.timecode = Timecode.from_source(source)

        # Shots keep the source's container, because they keep its codec, and
        # its name, so output from two mini cuts can share one directory
        source_file = Path(source.path)
        self.suffix = source_file.suffix or ".mp4"
        self.stem = source_file.stem

    # --- NAMING ---

    def filename_for(self, shot: Shot) -> str:
        """
        Returns the output filename for a shot.

        e.g. 'CHAS_006_hatem_Edit_E_v02_shot_007.mp4'.
        """
        return SHOT_FILENAME_TEMPLATE.format(
            stem=self.stem, index=shot.index, suffix=self.suffix
        )

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
        output_path = ensure_directory(self.output_dir) / self.filename_for(shot)

        start = self.timecode.frame_to_seconds(shot.start_frame)

        # The duration covers frame_count frames, not (end - start), which
        # would be one frame short every single time
        duration = self.timecode.frame_to_seconds(shot.frame_count)

        result = self.toolchain.run_ffmpeg(
            [
                "-y",
                # -ss goes before -i so ffmpeg seeks rather than decoding and
                # discarding everything up to the cut
                "-ss", Timecode.format_seconds(start),
                "-i", str(self.mezzanine_path),
                "-t", Timecode.format_seconds(duration),
                *COPY_ARGUMENTS,
                str(output_path),
            ],
            timeout=EXTRACT_TIMEOUT,
        )

        if result.returncode != 0:
            reason = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "no output"
            raise RuntimeError(f"Could not cut shot {shot.index}: {reason}")

        self._verify_length(shot, output_path)
        return output_path

    def _verify_length(self, shot: Shot, output_path: Path) -> None:
        """
        Confirms a written shot has exactly the frames it was asked for.

        Raises:
            RuntimeError: On any difference. A shot a frame out looks fine in a
                thumbnail and is wrong in every use of the clip, so it fails
                here rather than travelling downstream.
        """
        written = SourceProbe(self.toolchain).probe(output_path).frame_count

        if written != shot.frame_count:
            raise RuntimeError(
                f"Shot {shot.index} should be {shot.frame_count} frames "
                f"(frames {shot.start_frame}-{shot.end_frame}) but {written} were written"
            )

    def extract_all(self, shots: List[Shot]) -> List[Shot]:
        """
        Cuts every shot, recording the written path on each one.

        Args:
            shots: The full shot list.

        Returns:
            The same shots with `file` populated.

        Raises:
            RuntimeError: On the first shot that fails. A partial set of splits
                is worse than none, because the gap is easy to miss.
        """
        for shot in shots:
            shot.file = str(self.extract(shot))
            logging.info(f"Wrote shot {shot.index} of {len(shots)}: {Path(shot.file).name}")

        return shots
