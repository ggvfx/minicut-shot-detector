"""
SMPTE Timecode Engine.

The only place in the project where frames become time. Everything else works
in integer frames and calls in here at output boundaries — sidecar fields, UI
labels, ffmpeg arguments.

Frame rate mistakes (23.976 against 24) and off-by-one errors are the failure
this project is most exposed to, so the arithmetic is isolated here where it
can be unit tested on its own.
"""

import logging
from fractions import Fraction

from src.core.models import SourceInfo

# --- DROP FRAME RATES ---

# Drop-frame applies to 29.97 and 59.94 only. It skips timecode LABELS to keep
# the clock honest over long durations — it never skips actual frames.
DROP_FRAME_RATES = (Fraction(30000, 1001), Fraction(60000, 1001))

# Labels dropped at the start of each minute, except every tenth minute.
DROPPED_LABELS_PER_MINUTE = 2


class Timecode:
    """
    Frame and timecode arithmetic for one source's frame rate.

    Constructed once per job from the probed source, then used everywhere a
    frame number has to be shown or handed to ffmpeg.

    The rate is held as an exact Fraction, never a float. `fps = 23.976` looks
    harmless and drifts a frame roughly every forty seconds.
    """

    def __init__(self, numerator: int, denominator: int, start_timecode: str = "00:00:00:00"):
        """
        Args:
            numerator: Frame rate numerator as ffprobe reports it, e.g. 24000.
            denominator: Frame rate denominator, e.g. 1001.
            start_timecode: Source start timecode, added as an offset so values
                match what the editor sees.
        """
        self.rate = Fraction(numerator, denominator)
        self.start_timecode = start_timecode

    @classmethod
    def from_source(cls, source: SourceInfo) -> "Timecode":
        """Builds a Timecode from a probed source."""
        return cls(source.fps_numerator, source.fps_denominator, source.start_timecode)

    # --- RATE PROPERTIES ---

    @property
    def is_drop_frame(self) -> bool:
        """Whether this rate uses drop-frame timecode."""
        return self.rate in DROP_FRAME_RATES

    @property
    def labels_per_second(self) -> int:
        """
        Timecode labels in one second of this rate.

        The nominal integer, not the real rate: 23.976 counts 24 labels per
        second, and the difference is what timecode exists to hide.
        """
        # PSEUDOCODE
        # 1. Round the rate up to the nearest integer.
        raise NotImplementedError

    # --- FRAMES TO TIMECODE ---

    def frames_to_timecode(self, frames: int) -> str:
        """
        Converts a frame index to a timecode string.

        Args:
            frames: Frame index, 0 = first frame of the source.

        Returns:
            "HH:MM:SS:FF", or "HH:MM:SS;FF" when drop-frame.
        """
        # PSEUDOCODE
        # 1. Add the start_timecode offset, as frames.
        # 2. If drop-frame, add the labels that were skipped, so the label count
        #    matches wall clock: two per minute except every tenth minute.
        # 3. Divide down into hours / minutes / seconds / frames using
        #    labels_per_second.
        # 4. Format, with ";" before the frames field when drop-frame.
        raise NotImplementedError

    def timecode_to_frames(self, timecode: str) -> int:
        """
        Converts a timecode string back to a frame index. Inverse of the above.

        Used to read a source start timecode, and when a boundary is typed by
        hand during review.
        """
        # PSEUDOCODE
        # 1. Split on ":" or ";" — a ";" separator means drop-frame.
        # 2. Multiply out to a raw label count using labels_per_second.
        # 3. If drop-frame, subtract the labels that were never used.
        raise NotImplementedError

    # --- FRAMES TO SECONDS, FOR FFMPEG ---

    def frame_to_seconds(self, frame: int) -> Fraction:
        """
        Exact start time of a frame, as a Fraction.

        A Fraction rather than a float on purpose: this becomes an ffmpeg `-ss`
        argument, and a time landing a millionth of a second early puts the cut
        on the wrong side of the boundary.
        """
        return Fraction(frame) / self.rate

    @staticmethod
    def format_seconds(seconds: Fraction, decimal_places: int = 6) -> str:
        """
        Renders an exact time as a decimal string for an ffmpeg argument.

        Args:
            seconds: Exact time from frame_to_seconds().
            decimal_places: Six is comfortably finer than one frame at any
                broadcast rate.

        Notes:
            Never route through float() — that is the bug this class prevents.
            Scale as integers, then place the decimal point by hand.
        """
        # PSEUDOCODE
        # 1. Multiply by 10**decimal_places and round half-up, as integers.
        # 2. Split into whole and fractional parts and zero-pad the fraction.
        raise NotImplementedError
