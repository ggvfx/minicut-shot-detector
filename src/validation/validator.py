"""
Job Validation.

Proves that the shots written to disk are actually correct. Two kinds of check,
weakest first:

1. **Integrity** — plain arithmetic on the shot list. Durations sum to the
   source, no gaps, no overlaps, correct bounds. Catches the whole class of
   off-by-one bugs: a shot list where the frames do not add up is wrong no
   matter how good the detection was.

2. **Round trip** — join the splits back together and prove the result is
   frame-for-frame identical to the mezzanine. Integrity proves the NUMBERS
   add up; this proves the PIXELS do. It catches a dropped frame at a split
   point, a duplicated frame from a seek landing early, or shots written in the
   wrong order — none of which show in a thumbnail, and all of which ruin every
   clip downstream.

Both ship with v1. Any failure blocks the job: this stage never warns and
continues.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo, ValidationResult
from src.core.timecode import Timecode
from src.core.utils import ensure_directory

# --- TIMEOUTS ---

# Both are stream operations rather than encodes, but a feature-length source
# on a slow disk still needs room.
CONCAT_TIMEOUT = 1800.0
HASH_TIMEOUT = 1800.0

# One frame after a seek, so this is quick unless something is badly wrong.
FRAME_HASH_TIMEOUT = 120.0

# --- CHECK NAMES ---

# Stable keys, recorded in the sidecar's validation block.
CHECK_FRAMES_SUM = "frames_sum"
CHECK_NO_GAPS = "no_gaps"
CHECK_NO_OVERLAPS = "no_overlaps"
CHECK_BOUNDS = "bounds"
CHECK_BOUNDARY_FRAMES = "boundary_frames"
CHECK_ROUND_TRIP = "round_trip"

# The arithmetic checks, which run without touching a single video file.
INTEGRITY_CHECKS = (CHECK_FRAMES_SUM, CHECK_NO_GAPS, CHECK_NO_OVERLAPS, CHECK_BOUNDS)


class JobValidator:
    """
    Runs every correctness check for one job.

    Holds the toolchain, since the round trip needs ffmpeg for both the concat
    and the frame hashing.
    """

    def __init__(self, toolchain: MediaToolchain):
        self.toolchain = toolchain

    # --- PUBLIC API ---

    def validate_shot_list(self, shots: List[Shot], source: SourceInfo) -> ValidationResult:
        """
        Runs the arithmetic checks on a shot list.

        Called twice in a job: once immediately after detection, so a broken
        list stops the job before an hour of transcoding, and once on the shots
        as written.

        Returns:
            ValidationResult with one entry per check. `passed` is False if any
            check failed.
        """
        if not shots:
            return ValidationResult(
                passed=False,
                checks={name: False for name in INTEGRITY_CHECKS},
                failures=["The shot list is empty, so there is nothing to cut"],
            )

        ordered = sorted(shots, key=lambda shot: shot.start_frame)

        results = {
            CHECK_FRAMES_SUM: self._check_frames_sum(ordered, source.frame_count),
            CHECK_NO_GAPS: self._check_no_gaps(ordered),
            CHECK_NO_OVERLAPS: self._check_no_overlaps(ordered),
            CHECK_BOUNDS: self._check_bounds(ordered, source.frame_count),
        }

        failures = [failure for problems in results.values() for failure in problems]

        for name, problems in results.items():
            if problems:
                logging.error(f"Validation check {name} failed: {'; '.join(problems)}")

        return ValidationResult(
            passed=not failures,
            checks={name: not problems for name, problems in results.items()},
            failures=failures,
        )

    def validate_job(
        self,
        shots: List[Shot],
        source: SourceInfo,
        mezzanine_path: Path,
        work_dir: Path,
        full_round_trip: bool = False,
    ) -> ValidationResult:
        """
        Full validation after cutting: the arithmetic, then a pixel check.

        Args:
            full_round_trip: Rejoin every shot and compare every frame, rather
                than comparing the frames either side of each cut. Far slower
                and needs room for a second copy of the mezzanine; see
                `verify_boundary_frames` for why the default is enough.

        Returns:
            One combined ValidationResult. The check names record which pixel
            check ran, so a sidecar says how thoroughly a job was verified.

        Notes:
            The pixel check is skipped when the arithmetic has already failed.
            Its failure would be a consequence of the first problem rather than
            a second finding, and it is the expensive check of the two.
        """
        result = self.validate_shot_list(shots, source)
        check_name = CHECK_ROUND_TRIP if full_round_trip else CHECK_BOUNDARY_FRAMES

        if not result.passed:
            result.checks[check_name] = False
            result.failures.append(
                "Pixel check not attempted: the shot list itself does not add up"
            )
            return result

        if full_round_trip:
            passed, failure = self.verify_round_trip(mezzanine_path, shots, work_dir)
        else:
            passed, failure = self.verify_boundary_frames(mezzanine_path, shots, source)

        result.checks[check_name] = passed
        if not passed:
            result.passed = False
            result.failures.append(failure)

        return result

    # --- BOUNDARY FRAMES (the default pixel check) ---

    def verify_boundary_frames(
        self, mezzanine_path: Path, shots: List[Shot], source: SourceInfo
    ) -> Tuple[bool, Optional[str]]:
        """
        Compares the first and last frame of every shot against the mezzanine.

        Why this is enough: shots are stream copies, so the pixels inside one
        cannot change. Every realistic failure is at an edge — a shot starting
        or ending a frame out, shots written in the wrong order, or a shot
        missing entirely. All of those move a boundary frame.

        The full round trip decodes everything twice and writes a second copy
        of the mezzanine to disk; this decodes two frames per shot. On a 3.4
        minute cut that is the difference between 34 seconds and about one.

        Returns:
            (passed, failure description naming the shot and frame, or None).
        """
        timecode = Timecode.from_source(source)

        for shot in shots:
            if not shot.file:
                raise ValueError(f"Shot {shot.index} has no file to check")

            shot_path = Path(shot.file)

            edges = (
                ("first", shot.start_frame, 0),
                ("last", shot.end_frame, shot.frame_count - 1),
            )

            for label, source_frame, shot_frame in edges:
                expected = self._frame_hash_at(mezzanine_path, source_frame, timecode)
                actual = self._frame_hash_at(shot_path, shot_frame, timecode)

                if expected != actual:
                    return False, (
                        f"The {label} frame of shot {shot.index} is not frame "
                        f"{source_frame} of the source, so that cut landed in "
                        f"the wrong place"
                    )

        logging.info(f"Boundary frames verified for {len(shots)} shots")
        return True, None

    def _frame_hash_at(self, video_path: Path, frame_index: int, timecode: Timecode) -> str:
        """
        Checksum of one decoded frame.

        Seeking is exact because every frame of an all-intra file is a
        keyframe, and the shots cut from it inherit that.
        """
        seconds = timecode.frame_to_seconds(frame_index)

        result = self.toolchain.run_ffmpeg(
            [
                "-ss", Timecode.format_seconds(seconds),
                "-i", str(video_path),
                "-frames:v", "1",
                "-map", "0:v:0",
                "-an",
                "-c:v", "rawvideo",
                "-f", "framemd5",
                "-",
            ],
            timeout=FRAME_HASH_TIMEOUT,
        )

        hashes = self._parse_framemd5(result.stdout)

        if not hashes:
            raise RuntimeError(f"Could not read frame {frame_index} of {video_path.name}")

        return hashes[0]

    # --- INTEGRITY CHECKS ---

    @staticmethod
    def _check_frames_sum(shots: List[Shot], frame_count: int) -> List[str]:
        """
        Every source frame belongs to exactly one shot.

        Compared exactly, with no tolerance: a shot list one frame short is a
        shot list that is wrong somewhere.
        """
        total = sum(shot.frame_count for shot in shots)
        if total == frame_count:
            return []

        difference = total - frame_count
        direction = "more than" if difference > 0 else "fewer than"
        return [
            f"Shots total {total} frames, {abs(difference)} {direction} "
            f"the source's {frame_count}"
        ]

    @staticmethod
    def _check_no_gaps(shots: List[Shot]) -> List[str]:
        """
        Each shot starts on the frame immediately after the previous one ends.

        A gap means frames of the source belong to no shot at all, so they would
        simply never be written.
        """
        problems = []
        for current, following in zip(shots, shots[1:]):
            expected = current.end_frame + 1
            if following.start_frame > expected:
                missing = following.start_frame - expected
                problems.append(
                    f"Gap of {missing} frame{'s' if missing > 1 else ''} between "
                    f"shot {current.index} (ends {current.end_frame}) and "
                    f"shot {following.index} (starts {following.start_frame})"
                )
        return problems

    @staticmethod
    def _check_no_overlaps(shots: List[Shot]) -> List[str]:
        """
        No frame appears in two shots.

        An overlap means a frame is written twice, which the round trip would
        also catch — but naming the two shots here is far more useful than a
        hash mismatch later.
        """
        problems = []
        for current, following in zip(shots, shots[1:]):
            if following.start_frame <= current.end_frame:
                shared = current.end_frame - following.start_frame + 1
                problems.append(
                    f"Shot {current.index} (ends {current.end_frame}) and "
                    f"shot {following.index} (starts {following.start_frame}) "
                    f"share {shared} frame{'s' if shared > 1 else ''}"
                )
        return problems

    @staticmethod
    def _check_bounds(shots: List[Shot], frame_count: int) -> List[str]:
        """The shot list covers the source exactly, and no shot is inside out."""
        problems = []

        if shots[0].start_frame != 0:
            problems.append(
                f"First shot starts at frame {shots[0].start_frame}, not 0, "
                f"so the head of the source belongs to no shot"
            )

        last_frame = frame_count - 1
        if shots[-1].end_frame != last_frame:
            problems.append(
                f"Last shot ends at frame {shots[-1].end_frame}, not {last_frame}, "
                f"so the tail of the source is unaccounted for"
            )

        for shot in shots:
            if shot.end_frame < shot.start_frame:
                problems.append(
                    f"Shot {shot.index} ends at frame {shot.end_frame}, "
                    f"before it starts at {shot.start_frame}"
                )

        return problems

    # --- ROUND TRIP ---

    def verify_round_trip(
        self, mezzanine_path: Path, shots: List[Shot], work_dir: Path
    ) -> Tuple[bool, Optional[str]]:
        """
        Concatenates the splits and frame-hash compares against the mezzanine.

        Args:
            work_dir: Scratch space for the list file and rejoined video, both
                removed afterwards.

        Returns:
            (passed, failure description or None).
        """
        work_dir = ensure_directory(work_dir)
        list_path = work_dir / "concat.txt"
        rejoined_path = work_dir / f"rejoined{mezzanine_path.suffix}"

        try:
            self._build_concat_list(shots, list_path)
            self._concat_shots(list_path, rejoined_path)

            expected = self._frame_hashes(mezzanine_path)
            actual = self._frame_hashes(rejoined_path)

            return self._compare_frame_hashes(expected, actual)

        finally:
            # Scratch files, removed whether or not the check passed
            for path in (list_path, rejoined_path):
                path.unlink(missing_ok=True)

    def _build_concat_list(self, shots: List[Shot], list_path: Path) -> Path:
        """
        Writes the ffmpeg concat demuxer list file.

        Raises:
            ValueError: If a shot has no file recorded, which means it was
                never written and there is nothing to rejoin.

        Notes:
            Written in shot index order and quoted, because the concat demuxer
            treats unquoted spaces as argument breaks. Paths use forward
            slashes: the demuxer treats a backslash as an escape character even
            on Windows.
        """
        lines = []
        for shot in sorted(shots, key=lambda shot: shot.index):
            if not shot.file:
                raise ValueError(f"Shot {shot.index} has no file to rejoin")
            lines.append(f"file '{Path(shot.file).resolve().as_posix()}'")

        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return list_path

    def _concat_shots(self, list_path: Path, output_path: Path) -> Path:
        """
        Joins the shots back into a single file with a stream copy.

        Raises:
            RuntimeError: If ffmpeg cannot rejoin them, which is itself a
                finding — shots that will not concatenate are not a clean split.
        """
        result = self.toolchain.run_ffmpeg(
            [
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-map", "0:v:0",
                "-c", "copy",
                str(output_path),
            ],
            timeout=CONCAT_TIMEOUT,
        )

        if result.returncode != 0:
            reason = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "no output"
            raise RuntimeError(f"Could not rejoin the shots: {reason}")

        return output_path

    def _frame_hashes(self, video_path: Path) -> List[str]:
        """
        Per-frame checksums of the decoded picture, in order.

        Notes:
            Uses ffmpeg's framemd5 muxer rather than decoding in Python — far
            faster, and a hash of the decoded pixels, so an identical picture
            always hashes identically whatever the container did.

            Video only. Audio is cut on packet boundaries rather than frames,
            so hashing it would report a difference on every correct job.
        """
        result = self.toolchain.run_ffmpeg(
            [
                "-i", str(video_path),
                "-map", "0:v:0",
                "-an",
                "-c:v", "rawvideo",
                "-f", "framemd5",
                "-",
            ],
            timeout=HASH_TIMEOUT,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Could not hash the frames of {video_path.name}")

        return self._parse_framemd5(result.stdout)

    @staticmethod
    def _parse_framemd5(output: str) -> List[str]:
        """
        Pulls the hashes out of framemd5 output, one per frame in order.

        Rows look like "0, 0, 0, 1, 115200, d41d8cd98f00b204e9800998ecf8427e",
        with the hash last. Comment lines carry the header and are skipped.
        """
        return [
            line.split(",")[-1].strip()
            for line in output.splitlines()
            if line.strip() and not line.startswith("#")
        ]

    @staticmethod
    def _compare_frame_hashes(
        expected: List[str], actual: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Compares two hash lists and reports the first divergence.

        Returns:
            (True, None) when identical, otherwise (False, description) naming
            the first differing frame — that number points straight at the split
            that went wrong.
        """
        if len(expected) != len(actual):
            difference = len(actual) - len(expected)
            wording = "more than" if difference > 0 else "fewer than"
            return False, (
                f"Rejoining the shots gives {len(actual)} frames, "
                f"{abs(difference)} {wording} the mezzanine's {len(expected)} — "
                f"frames were dropped or duplicated at a cut"
            )

        for index, (left, right) in enumerate(zip(expected, actual)):
            if left != right:
                return False, (
                    f"Frame {index} differs between the mezzanine and the rejoined "
                    f"shots, so a cut near it landed on the wrong frames"
                )

        return True, None
