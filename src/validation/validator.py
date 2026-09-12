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

# --- CHECK NAMES ---

# Stable keys, recorded in the sidecar's validation block.
CHECK_FRAMES_SUM = "frames_sum"
CHECK_NO_GAPS = "no_gaps"
CHECK_NO_OVERLAPS = "no_overlaps"
CHECK_BOUNDS = "bounds"
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
        self, shots: List[Shot], source: SourceInfo, mezzanine_path: Path, work_dir: Path
    ) -> ValidationResult:
        """
        Full validation after cutting: arithmetic plus the round trip.

        Returns:
            One combined ValidationResult covering both kinds of check.
        """
        # PSEUDOCODE
        # 1. result = validate_shot_list(shots, source).
        # 2. Skip the round trip if the arithmetic already failed — its failure
        #    would just be a confusing consequence of the first one.
        # 3. Otherwise run verify_round_trip() and fold the outcome in.
        raise NotImplementedError

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
        # PSEUDOCODE
        # 1. _build_concat_list() then _concat_shots() into work_dir.
        # 2. _frame_hashes() for the mezzanine and for the rejoined file.
        # 3. _compare_frame_hashes(), then clean up the temporary files.
        raise NotImplementedError

    def _build_concat_list(self, shots: List[Shot], list_path: Path) -> Path:
        """
        Writes the ffmpeg concat demuxer list file.

        Notes:
            Paths are written in shot index order and quoted — the concat
            demuxer treats unquoted spaces as argument breaks.
        """
        # PSEUDOCODE
        # 1. Sort shots by index.
        # 2. Write one "file '<absolute path>'" line per shot.
        raise NotImplementedError

    def _concat_shots(self, list_path: Path, output_path: Path) -> Path:
        """Joins the shots back into a single file with a stream copy."""
        # PSEUDOCODE
        # 1. run ffmpeg: -f concat -safe 0 -i <list> -c copy <output>
        raise NotImplementedError

    def _frame_hashes(self, video_path: Path) -> List[str]:
        """
        Per-frame checksums for a video, in order.

        Notes:
            Uses ffmpeg's framemd5 muxer rather than decoding in Python — far
            faster, and a stable hash of the decoded pixels, so an identical
            picture always hashes identically.
        """
        # PSEUDOCODE
        # 1. run ffmpeg: -i <video> -f framemd5 -
        # 2. Skip comment lines, take the hash column from each remaining row.
        raise NotImplementedError

    def _compare_frame_hashes(self, expected: List[str], actual: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Compares two hash lists and reports the first divergence.

        Returns:
            (True, None) when identical, otherwise (False, description) naming
            the first differing frame — that number points straight at the split
            that went wrong.
        """
        # PSEUDOCODE
        # 1. Compare lengths first; a difference means a dropped or duplicated
        #    frame, so report the count difference.
        # 2. Walk both lists and return the first index that differs.
        raise NotImplementedError
