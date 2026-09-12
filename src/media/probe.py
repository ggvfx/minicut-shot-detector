"""
Source Inspection and Preprocessing Checks.

Stage 1 of the pipeline. Reads everything we need to know about the source
before any work starts: frame rate, duration, timecode, letterboxing and the
disk cost of the job.

Nothing here modifies the source. Variable frame rate sources are reported and
refused rather than rewritten — normalising them is a whole feature, and one
that waits until a real VFR file turns up.
"""

import logging
from pathlib import Path
from typing import Optional

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import SourceInfo

# --- CROP DETECTION SETTINGS ---

# cropdetect is sampled at several points rather than one. A single sample can
# land on a fade or a black frame and report the whole picture as letterboxed.
CROP_SAMPLE_POINTS = 5
CROP_SAMPLE_SECONDS = 10


class SourceProbe:
    """
    Reads technical metadata from source files.

    Holds the toolchain so a job's probe, crop detection and frame count all
    run through the same resolved ffprobe binary.
    """

    def __init__(self, toolchain: MediaToolchain):
        self.toolchain = toolchain

    # --- PROBING ---

    def probe(self, source_path: Path) -> SourceInfo:
        """
        Reads technical metadata from the source file.

        Args:
            source_path: The mini cut to inspect.

        Returns:
            SourceInfo, populated from ffprobe's JSON output.

        Raises:
            FileNotFoundError: If the source does not exist.
            ValueError: If ffprobe finds no video stream.
        """
        # PSEUDOCODE
        # 1. run_ffprobe: -v error -print_format json -show_streams -show_format
        # 2. Pick the first stream where codec_type == "video".
        # 3. Read width, height, codec_name, nb_frames.
        # 4. Split r_frame_rate ("24000/1001") into numerator and denominator
        #    and keep both — never divide them into a float here.
        # 5. Compare r_frame_rate with avg_frame_rate for is_variable_frame_rate.
        # 6. Read the timecode tag if present, else "00:00:00:00".
        # 7. Return a SourceInfo.
        raise NotImplementedError

    # --- MASKING ---

    def detect_crop(self, source_path: Path, duration_frames: int) -> Optional[str]:
        """
        Finds letterbox or pillarbox bars with ffmpeg's cropdetect filter.

        The result is shown in the UI for confirmation, never silently applied
        and never typed in by hand — a wrong mask quietly degrades detection.

        Args:
            source_path: The mini cut.
            duration_frames: Used to space the samples across the whole file.

        Returns:
            Crop string "w:h:x:y", or None when the frame is already full.
        """
        # PSEUDOCODE
        # 1. Pick CROP_SAMPLE_POINTS start times spread across the duration.
        # 2. For each, run ffmpeg -ss <start> -t CROP_SAMPLE_SECONDS
        #    -vf cropdetect -f null - and collect the crop=... values on stderr.
        # 3. Take the most common value across all samples.
        # 4. Return None if it matches the full frame.
        raise NotImplementedError

    # --- DISK ESTIMATION ---

    def estimate_disk_required(self, source: SourceInfo) -> float:
        """
        Estimates gigabytes needed: the mezzanine plus the splits.

        Reported before the job starts, so the user finds out now rather than
        when the drive fills mid-transcode.

        Returns:
            Estimated gigabytes.
        """
        # PSEUDOCODE
        # 1. Duration in minutes from frame_count and the exact fps.
        # 2. Scale GB_PER_MINUTE_PRORES_1080P25 by pixel count relative to 1080p.
        # 3. Double it — the splits together are roughly a second copy.
        raise NotImplementedError
