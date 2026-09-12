"""
Source Inspection and Preprocessing Checks.

Stage 1 of the pipeline. Reads everything we need to know about the source
before any work starts: frame rate, duration, timecode, letterboxing and the
disk cost of the job.

Nothing here modifies the source.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

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

    def count_frames_exactly(self, source_path: Path) -> int:
        """
        Counts frames by decoding, for sources where nb_frames is missing or lies.

        Slow — it walks the whole file — so it is only used when the container
        metadata cannot be trusted. An incorrect frame count silently shifts
        every boundary in the job.
        """
        # PSEUDOCODE
        # 1. run_ffprobe: -count_frames -select_streams v:0
        #    -show_entries stream=nb_read_frames
        # 2. Parse and return the integer.
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

    # --- VARIABLE FRAME RATE ---

    def normalise_variable_frame_rate(
        self, source_path: Path, output_path: Path, target_rate: Tuple[int, int]
    ) -> Path:
        """
        Rewrites a variable frame rate source to constant frame rate.

        VFR sources have no stable frame-to-time mapping, so every boundary
        drifts. They are either normalised here first or rejected outright.

        Returns:
            Path to the normalised file, which becomes the source for the rest
            of the job.
        """
        # PSEUDOCODE
        # 1. run ffmpeg with -vsync cfr and -r <target_rate> to the mezzanine codec.
        # 2. Re-probe the result and assert the frame count matches expectation.
        raise NotImplementedError

    # --- DISK ESTIMATION ---

    def estimate_disk_required(self, source: SourceInfo, stills_per_shot: int = 3) -> float:
        """
        Estimates gigabytes needed: mezzanine plus splits plus stills.

        Reported before the job starts, so the user finds out now rather than
        when the drive fills mid-transcode.

        Returns:
            Estimated gigabytes.
        """
        # PSEUDOCODE
        # 1. Duration in minutes from frame_count and the exact fps.
        # 2. Scale GB_PER_MINUTE_PRORES_1080P25 by pixel count relative to 1080p.
        # 3. Double it — the splits together are roughly a second copy.
        # 4. Add a small allowance for stills.
        raise NotImplementedError
