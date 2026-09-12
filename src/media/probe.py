"""
Source Inspection and Preprocessing Checks.

Stage 1 of the pipeline. Reads everything we need to know about the source
before any work starts: frame rate, duration, timecode, letterboxing and the
disk cost of the job.

Nothing here modifies the source. Variable frame rate is reported, not fixed —
this module states what a file is, and the pipeline decides whether to refuse
it. Normalising VFR is a whole feature, and one that waits until a real VFR
source turns up.
"""

import json
import logging
import re
import shutil
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

from src.core.config import GB_PER_MINUTE_INTRA_1080P24, REFERENCE_RATE
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import ProbeReport, SourceInfo
from src.core.timecode import Timecode

# --- CROP DETECTION SETTINGS ---

# cropdetect is sampled at several points rather than one. A single sample can
# land on a fade or a dark frame and report the whole picture as letterboxed.
CROP_SAMPLE_POINTS = 5
CROP_SAMPLE_SECONDS = 10

# round=2 keeps the reported crop close to the true edge. cropdetect defaults to
# rounding to a multiple of 16, which can eat several rows of real picture.
CROP_FILTER = "cropdetect=round=2"

# Matches the "crop=w:h:x:y" cropdetect prints on stderr for every frame.
CROP_PATTERN = re.compile(r"crop=(\d+:\d+:\d+:\d+)")

# --- DISK ESTIMATION ---

# The reference figure in config is quoted for 1080p at 24 fps, so both
# resolution and frame rate scale it.
REFERENCE_PIXELS = 1920 * 1080

# A job writes the mezzanine and then the splits, which together are roughly a
# second copy of it.
DISK_COPIES = 2


class SourceProbe:
    """
    Reads technical metadata from source files.

    Holds the toolchain so a job's probe and crop detection run through the same
    resolved ffprobe binary.
    """

    def __init__(self, toolchain: MediaToolchain):
        self.toolchain = toolchain

    # --- FULL INSPECTION ---

    def inspect(self, source_path: Path, output_dir: Optional[Path] = None) -> ProbeReport:
        """
        Everything the UI needs to decide whether to start a job.

        Probes the source, detects masking, estimates the disk cost and
        compares it against the output volume.

        Args:
            source_path: The mini cut to inspect.
            output_dir: Where the job would write, for the free space check.

        Returns:
            ProbeReport. `can_split` is False only when the source genuinely
            cannot be cut accurately; everything else is a warning the user may
            proceed past.
        """
        source = self.probe(source_path)

        # A variable frame rate source has no stable frame-to-time mapping, so
        # every boundary would drift. This is a refusal, not a warning.
        refusal = None
        if source.is_variable_frame_rate:
            refusal = (
                "This source has a variable frame rate, so frame numbers do not map "
                "reliably to time. Convert it to constant frame rate first."
            )

        crop = None if refusal else self.detect_crop(source)
        source.detected_crop = crop

        estimated_gb = self.estimate_disk_required(source)
        free_gb = None
        warnings: List[str] = []

        if output_dir is not None and output_dir.is_dir():
            free_gb = shutil.disk_usage(output_dir).free / (1024 ** 3)
            if estimated_gb > free_gb:
                warnings.append(
                    f"This job needs about {estimated_gb:.0f} GB but only "
                    f"{free_gb:.0f} GB is free on the output volume."
                )

        # Duration is a length, not a position, so it is measured from zero.
        # Using the source's own start timecode here would report 10:00:02:00
        # for a two second clip that happens to start at 10:00:00:00.
        length = Timecode(source.fps_numerator, source.fps_denominator)

        return ProbeReport(
            source=source,
            detected_crop=crop,
            duration_timecode=length.frames_to_timecode(source.frame_count),
            estimated_gb=estimated_gb,
            free_gb=free_gb,
            can_split=refusal is None,
            refusal_reason=refusal,
            warnings=warnings,
        )

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
            ValueError: If ffprobe fails, the output is unreadable, or the file
                has no video stream.
        """
        if not source_path.is_file():
            raise FileNotFoundError(f"Source not found: {source_path}")

        result = self.toolchain.run_ffprobe(
            [
                "-v", "error",
                "-print_format", "json",
                "-show_streams",
                "-show_format",
                str(source_path),
            ],
            timeout=60.0,
        )

        if result.returncode != 0:
            raise ValueError(f"ffprobe could not read {source_path}: {result.stderr.strip()}")

        try:
            probed = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError(f"ffprobe returned unreadable output for {source_path}: {error}")

        streams = probed.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if video is None:
            raise ValueError(f"No video stream in {source_path}")

        numerator, denominator = self._parse_rate(video.get("r_frame_rate"), source_path)

        source = SourceInfo(
            path=str(source_path),
            width=int(video["width"]),
            height=int(video["height"]),
            fps_numerator=numerator,
            fps_denominator=denominator,
            frame_count=self._frame_count(video, Fraction(numerator, denominator), source_path),
            codec=video.get("codec_name", "unknown"),
            pixel_format=video.get("pix_fmt", "yuv420p"),
            start_timecode=self._start_timecode(streams, probed.get("format", {})),
            is_variable_frame_rate=self._is_variable_frame_rate(video),
        )

        logging.info(
            f"Probed {source_path.name}: {source.width}x{source.height}, "
            f"{numerator}/{denominator} fps, {source.frame_count} frames, "
            f"start {source.start_timecode}"
        )
        return source

    # --- PARSING HELPERS ---

    @staticmethod
    def _parse_rate(rate: Optional[str], source_path: Path):
        """
        Splits an ffprobe rate string such as "24000/1001" into two integers.

        Kept as a pair rather than divided, because 24000/1001 is not 23.976 and
        the difference drifts a frame roughly every forty seconds.

        Raises:
            ValueError: If the rate is missing, malformed or zero.
        """
        if not rate or "/" not in rate:
            raise ValueError(f"No usable frame rate in {source_path} (got {rate!r})")

        numerator, denominator = rate.split("/", 1)
        try:
            numerator, denominator = int(numerator), int(denominator)
        except ValueError:
            raise ValueError(f"Unreadable frame rate {rate!r} in {source_path}")

        if numerator <= 0 or denominator <= 0:
            raise ValueError(f"Frame rate {rate!r} in {source_path} is not usable")

        return numerator, denominator

    def _frame_count(self, video: dict, rate: Fraction, source_path: Path) -> int:
        """
        The number of frames in the video stream.

        Prefers the container's own `nb_frames`. Some containers omit it, in
        which case the count is derived from the duration — less trustworthy,
        so it is logged rather than passed over in silence.

        Raises:
            ValueError: If neither is available.
        """
        nb_frames = video.get("nb_frames")
        if nb_frames is not None:
            try:
                return int(nb_frames)
            except ValueError:
                logging.warning(f"Unreadable nb_frames {nb_frames!r} in {source_path}")

        duration = video.get("duration")
        if duration is not None:
            try:
                frames = int(round(float(duration) * rate))
            except ValueError:
                raise ValueError(f"Unreadable duration {duration!r} in {source_path}")

            logging.warning(
                f"{source_path.name} has no frame count; derived {frames} from its duration"
            )
            return frames

        raise ValueError(f"Cannot determine a frame count for {source_path}")

    @staticmethod
    def _is_variable_frame_rate(video: dict) -> bool:
        """
        Whether the container reports a variable frame rate.

        r_frame_rate is the base rate, avg_frame_rate the realised average.
        When they disagree the file has no stable frame-to-time mapping, so
        every boundary would drift.

        An unknown average (0/0, as some containers report) is not treated as
        VFR — there is nothing to compare it against.
        """
        try:
            base = Fraction(video.get("r_frame_rate", "0/0"))
            average = Fraction(video.get("avg_frame_rate", "0/0"))
        except (ValueError, ZeroDivisionError):
            return False

        if base == 0 or average == 0:
            return False

        return base != average

    @staticmethod
    def _start_timecode(streams: List[dict], container: dict) -> str:
        """
        The source start timecode, searched in the three places it can hide.

        ffmpeg writes it to the video stream's tags and to a separate `tmcd`
        data stream; some files carry it only in the container tags.

        Returns:
            "HH:MM:SS:FF", or "00:00:00:00" when the file carries none.
        """
        for stream in streams:
            timecode = stream.get("tags", {}).get("timecode")
            if timecode:
                return timecode

        timecode = container.get("tags", {}).get("timecode")
        return timecode if timecode else "00:00:00:00"

    # --- MASKING ---

    def detect_crop(self, source: SourceInfo) -> Optional[str]:
        """
        Finds letterbox or pillarbox bars with ffmpeg's cropdetect filter.

        The result is shown in the UI for confirmation, never silently applied
        and never typed in by hand — a wrong mask quietly degrades detection.

        Sampled at several points across the file, because one sample can land
        on a fade or a dark frame and report the whole picture as letterboxed.

        Args:
            source: The probed source.

        Returns:
            Crop string "w:h:x:y", or None when the frame is already full.
        """
        source_path = Path(source.path)
        rate = Fraction(source.fps_numerator, source.fps_denominator)
        total_seconds = float(source.frame_count / rate)

        found: Counter = Counter()

        for offset in self._sample_offsets(total_seconds):
            result = self.toolchain.run_ffmpeg(
                [
                    "-ss", f"{offset:.3f}",
                    "-t", str(CROP_SAMPLE_SECONDS),
                    "-i", str(source_path),
                    "-vf", CROP_FILTER,
                    "-f", "null",
                    "-",
                ],
                timeout=180.0,
            )
            # cropdetect reports on stderr, one line per frame
            found.update(CROP_PATTERN.findall(result.stderr))

        if not found:
            logging.warning(f"cropdetect found nothing in {source_path.name}")
            return None

        crop, _ = found.most_common(1)[0]

        full_frame = f"{source.width}:{source.height}:0:0"
        if crop == full_frame:
            logging.info(f"{source_path.name} is full frame, no mask needed")
            return None

        logging.info(f"{source_path.name} appears masked: crop={crop}")
        return crop

    @staticmethod
    def _sample_offsets(total_seconds: float) -> List[float]:
        """
        Start times for the cropdetect samples, spread across the file.

        Deliberately avoids the very first and last moments, which are the most
        likely places to find a fade to black.
        """
        if total_seconds <= CROP_SAMPLE_SECONDS:
            return [0.0]

        usable = max(total_seconds - CROP_SAMPLE_SECONDS, 0.0)
        return [
            usable * (point + 1) / (CROP_SAMPLE_POINTS + 1)
            for point in range(CROP_SAMPLE_POINTS)
        ]

    # --- DISK ESTIMATION ---

    def estimate_disk_required(self, source: SourceInfo) -> float:
        """
        Estimates gigabytes needed: the mezzanine plus the splits.

        Reported before the job starts, so the user finds out now rather than
        when the drive fills mid-transcode.

        The reference figure is an all-intra h264 mezzanine at 1080p24, so
        both resolution and frame rate scale it.

        Returns:
            Estimated gigabytes.
        """
        rate = Fraction(source.fps_numerator, source.fps_denominator)
        minutes = float(source.frame_count / rate / 60)

        pixel_scale = (source.width * source.height) / REFERENCE_PIXELS
        rate_scale = float(rate) / REFERENCE_RATE

        return GB_PER_MINUTE_INTRA_1080P24 * minutes * pixel_scale * rate_scale * DISK_COPIES
