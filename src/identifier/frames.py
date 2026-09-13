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
"""

import logging
from pathlib import Path
from typing import List

from src.core.ffmpeg_tools import MediaToolchain
from src.core.utils import ensure_directory

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
            RuntimeError: If the file cannot be read, or no frame could be
                extracted from it.
        """
        duration = self.duration_seconds(source_path)
        ensure_directory(output_dir)

        stem = source_path.stem
        written: List[Path] = []

        for index, offset in enumerate(self._offsets(duration, count)):
            target = output_dir / f"{stem}_f{index:02d}.jpg"

            if self._write_frame(source_path, offset, target):
                written.append(target)

        if not written:
            raise RuntimeError(f"No frames could be read from {source_path}")

        logging.info(f"Sampled {len(written)} frames from {source_path.name}")
        return written

    def thumbnail(self, source_path: Path, output_path: Path) -> Path:
        """
        One representative frame, for the breakdown export.

        Taken from the middle of the shot. A first frame is often a
        part-completed camera move or a character entering, and reads as a
        worse summary of a shot than anything from its middle.

        Raises:
            RuntimeError: If no frame could be written.
        """
        ensure_directory(output_path.parent)
        midpoint = self.duration_seconds(source_path) / 2

        if not self._write_frame(source_path, midpoint, output_path):
            raise RuntimeError(f"No thumbnail could be read from {source_path}")

        return output_path

    # --- TIMING ---

    def duration_seconds(self, source_path: Path) -> float:
        """
        How long the shot runs.

        Raises:
            RuntimeError: If the file has no readable duration — a still image,
                an audio-only file, or something that is not media at all.
                Saying so here names the file, rather than producing an empty
                frame list that reads downstream as an undescribable shot.
        """
        result = self.toolchain.run_ffprobe([
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(source_path),
        ])

        try:
            duration = float((result.stdout or "").strip())
        except ValueError:
            raise RuntimeError(f"Could not read a duration from {source_path}") from None

        if duration <= 0:
            raise RuntimeError(f"{source_path} has no duration")

        return duration

    @staticmethod
    def _offsets(duration: float, count: int) -> List[float]:
        """
        Where in the shot to take each frame.

        Notes:
            Spread across the middle of the shot, trimmed at both ends: the
            first and last frames of a cut often catch a part-completed motion
            or a residual blend from the edit, which describes the transition
            rather than the shot.

            One frame is taken from the midpoint rather than the start, which
            is the case for a still reference image and for a very short shot.
        """
        if count <= 1:
            return [duration / 2]

        trim = duration * EDGE_TRIM_FRACTION
        first, last = trim, duration - trim
        step = (last - first) / (count - 1)

        return [first + step * index for index in range(count)]

    # --- WRITING ---

    def _write_frame(self, source_path: Path, offset: float, target: Path) -> bool:
        """
        Writes one scaled frame, and says whether it arrived.

        Notes:
            `-ss` before `-i` seeks by keyframe, which is approximate and
            fast. That is the right trade here: this describes a shot rather
            than cutting one, and a frame either side of the intended offset
            shows the same picture. The splitter is where exactness matters.

            A failure returns False rather than raising, so one unreadable
            offset near the end of a file does not lose the frames that did
            come out.
        """
        result = self.toolchain.run_ffmpeg([
            "-ss", f"{offset:.3f}",
            "-i", str(source_path),
            "-frames:v", "1",
            "-vf", f"scale={SAMPLE_WIDTH}:-2",
            "-q:v", "4",
            "-y", str(target),
        ])

        if result.returncode != 0 or not target.is_file():
            logging.debug(f"No frame at {offset:.3f}s in {source_path.name}")
            return False

        return True
