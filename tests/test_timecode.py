"""
Tests for the Timecode Engine.

Everything downstream trusts this arithmetic, so the cases here are the ones
that would otherwise be found by watching a clip start a frame late: the
23.976 / 24 distinction, drop-frame label skipping, and exact seek times.
"""

from fractions import Fraction

import pytest

from src.core.timecode import Timecode

# --- FIXTURES ---


@pytest.fixture
def pal():
    """25 fps, the simplest case — no rounding, no drop-frame."""
    return Timecode(25, 1)


@pytest.fixture
def film():
    """23.976, where the real rate and the label rate differ."""
    return Timecode(24000, 1001)


@pytest.fixture
def ntsc():
    """29.97 drop-frame, the awkward one."""
    return Timecode(30000, 1001)


# --- RATE PROPERTIES ---


def test_rate_is_exact_not_rounded(film):
    """The rate stays a rational; 23.976 as a float drifts a frame every ~40s."""
    assert film.rate == Fraction(24000, 1001)
    assert film.rate != Fraction(24, 1)


def test_labels_per_second_is_the_nominal_rate(pal, film, ntsc):
    """23.976 counts 24 labels per second — hiding that is what timecode is for."""
    assert pal.labels_per_second == 25
    assert film.labels_per_second == 24
    assert ntsc.labels_per_second == 30
    assert Timecode(60000, 1001).labels_per_second == 60


def test_only_2997_and_5994_are_drop_frame(pal, film, ntsc):
    """Drop-frame is not a property of being NTSC — 23.976 is non-drop."""
    assert ntsc.is_drop_frame is True
    assert Timecode(60000, 1001).is_drop_frame is True
    assert pal.is_drop_frame is False
    assert film.is_drop_frame is False, "23.976 is not a drop-frame rate"


def test_dropped_labels_scale_with_the_rate(ntsc):
    """59.94 drops four labels a minute where 29.97 drops two."""
    assert ntsc.dropped_labels_per_minute == 2
    assert Timecode(60000, 1001).dropped_labels_per_minute == 4
    assert Timecode(25, 1).dropped_labels_per_minute == 0


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        Timecode(0, 1)
    with pytest.raises(ValueError):
        Timecode(-25, 1)


# --- NON-DROP CONVERSION ---


def test_frame_zero_is_the_start(pal):
    assert pal.frames_to_timecode(0) == "00:00:00:00"


def test_last_frame_of_a_second(pal):
    """Frame 24 at 25 fps is still second zero — the classic off-by-one."""
    assert pal.frames_to_timecode(24) == "00:00:00:24"
    assert pal.frames_to_timecode(25) == "00:00:01:00"


def test_one_minute(pal):
    assert pal.frames_to_timecode(1500) == "00:01:00:00"


def test_one_hour(pal):
    assert pal.frames_to_timecode(25 * 60 * 60) == "01:00:00:00"


def test_23976_counts_24_labels_per_second(film):
    """
    At 23.976 a second of timecode is 24 frames, not 23.976 of them.

    Getting this wrong is how a clip ends up a frame short every 40 seconds.
    """
    assert film.frames_to_timecode(23) == "00:00:00:23"
    assert film.frames_to_timecode(24) == "00:00:01:00"


def test_non_drop_uses_a_colon(pal, film):
    assert ":" in pal.frames_to_timecode(100)
    assert ";" not in film.frames_to_timecode(100)


# --- DROP FRAME CONVERSION ---


def test_drop_frame_uses_a_semicolon(ntsc):
    """The separator is how an editor tells drop from non-drop at a glance."""
    assert ntsc.frames_to_timecode(0) == "00:00:00;00"


def test_first_minute_drops_nothing(ntsc):
    """Minute zero keeps every label, so frame 1799 is still 59;29."""
    assert ntsc.frames_to_timecode(1799) == "00:00:59;29"


def test_second_minute_starts_at_frame_02(ntsc):
    """
    Labels ;00 and ;01 are skipped at the start of minute one.

    Frame 1800 is the first frame of the second minute and must be labelled
    00:01:00;02, not 00:01:00;00.
    """
    assert ntsc.frames_to_timecode(1800) == "00:01:00;02"


def test_tenth_minute_keeps_its_labels(ntsc):
    """
    Every tenth minute drops nothing, which is what keeps the clock honest.

    17982 frames is exactly ten minutes of 29.97.
    """
    assert ntsc.frames_to_timecode(17982) == "00:10:00;00"


def test_drop_frame_stays_close_to_wall_clock(ntsc):
    """
    An hour of drop-frame timecode is an hour of real time, near enough.

    107892 frames at 30000/1001 is 3600.0 seconds; the label must read 01:00:00;00.
    """
    assert ntsc.frames_to_timecode(107892) == "01:00:00;00"


# --- ROUND TRIPS ---


@pytest.mark.parametrize("frame", [0, 1, 24, 25, 1499, 1500, 1799, 1800, 17981, 17982, 107892])
def test_round_trip_non_drop(pal, frame):
    """Every frame survives conversion to timecode and back."""
    assert pal.timecode_to_frame_index(pal.frames_to_timecode(frame)) == frame


@pytest.mark.parametrize("frame", [0, 1, 1799, 1800, 1801, 17981, 17982, 17983, 107892])
def test_round_trip_drop_frame(ntsc, frame):
    """Drop-frame round trips too, including across the minute boundaries."""
    assert ntsc.timecode_to_frame_index(ntsc.frames_to_timecode(frame)) == frame


@pytest.mark.parametrize("frame", [0, 7, 100, 5000, 90000])
def test_round_trip_23976(film, frame):
    assert film.timecode_to_frame_index(film.frames_to_timecode(frame)) == frame


# --- START TIMECODE OFFSET ---


def test_start_timecode_offsets_the_display():
    """A source starting at 10:00:00:00 shows its first frame as exactly that."""
    timecode = Timecode(25, 1, start_timecode="10:00:00:00")

    assert timecode.frames_to_timecode(0) == "10:00:00:00"
    assert timecode.frames_to_timecode(1500) == "10:01:00:00"


def test_frame_index_is_recovered_from_an_offset_display():
    """Typing a displayed timecode gets back the frame index, not the label count."""
    timecode = Timecode(25, 1, start_timecode="10:00:00:00")

    assert timecode.timecode_to_frame_index("10:00:00:00") == 0
    assert timecode.timecode_to_frame_index("10:01:00:00") == 1500


def test_start_timecode_is_validated_on_construction():
    """A malformed start timecode fails now, not in the middle of a job."""
    with pytest.raises(ValueError):
        Timecode(25, 1, start_timecode="not a timecode")


# --- PARSING ---


def test_both_separators_are_accepted(ntsc):
    """Editors and ffprobe disagree about ';' versus ':' — accept either."""
    assert ntsc.timecode_to_frames("00:01:00;02") == ntsc.timecode_to_frames("00:01:00:02")


@pytest.mark.parametrize("bad", ["", "10:00:00", "10:00:00:00:00", "aa:bb:cc:dd", "10;00;00"])
def test_malformed_timecodes_are_rejected(pal, bad):
    with pytest.raises(ValueError):
        pal.timecode_to_frames(bad)


@pytest.mark.parametrize("bad", ["25:00:00:00", "00:60:00:00", "00:00:60:00", "00:00:00:25"])
def test_out_of_range_fields_are_rejected(pal, bad):
    """A frames field of 25 at 25 fps is not a valid label."""
    with pytest.raises(ValueError):
        pal.timecode_to_frames(bad)


def test_dropped_labels_are_rejected(ntsc):
    """
    00:01:00;00 does not exist at 29.97 — that label is skipped.

    Accepting it silently would place a boundary two frames out.
    """
    with pytest.raises(ValueError):
        ntsc.timecode_to_frames("00:01:00;00")

    # The tenth minute keeps its labels, so this one is real
    assert ntsc.timecode_to_frames("00:10:00;00") == 17982


# --- SECONDS FOR FFMPEG ---


def test_frame_to_seconds_is_exact(film):
    """One frame at 23.976 is exactly 1001/24000 seconds, not 0.0417."""
    assert film.frame_to_seconds(1) == Fraction(1001, 24000)
    assert film.frame_to_seconds(24) == Fraction(1001, 1000)


def test_frame_to_seconds_is_never_a_float(pal):
    """A float here is the bug this module exists to prevent."""
    assert isinstance(pal.frame_to_seconds(7), Fraction)


def test_format_seconds_rounds_half_up(pal):
    assert Timecode.format_seconds(Fraction(1, 10)) == "0.100000"
    assert Timecode.format_seconds(Fraction(1, 3)) == "0.333333"
    assert Timecode.format_seconds(Fraction(2, 3)) == "0.666667"


def test_format_seconds_keeps_frame_accuracy(film):
    """A frame time survives formatting with room to spare at six places."""
    assert Timecode.format_seconds(film.frame_to_seconds(1)) == "0.041708"
    assert Timecode.format_seconds(film.frame_to_seconds(0)) == "0.000000"


def test_format_seconds_pads_the_fraction(pal):
    """A short fraction must be zero-padded or ffmpeg reads a different time."""
    assert Timecode.format_seconds(Fraction(3, 2)) == "1.500000"
    assert Timecode.format_seconds(Fraction(2, 1)) == "2.000000"


def test_format_seconds_rejects_bad_input():
    with pytest.raises(ValueError):
        Timecode.format_seconds(Fraction(-1, 2))
    with pytest.raises(ValueError):
        Timecode.format_seconds(Fraction(1, 2), decimal_places=0)


# --- GUARDS ---


def test_negative_frame_index_is_rejected(pal):
    with pytest.raises(ValueError):
        pal.frames_to_timecode(-1)
