"""
Tests for the FFmpeg Toolchain.

The encoder parser is tested against captured output rather than a live ffmpeg,
so these run identically on a machine without ffmpeg installed.
"""

from src.core.ffmpeg_tools import MediaToolchain

# --- SAMPLE OUTPUT ---

# Trimmed from real `ffmpeg -encoders` output, including the header and the flag
# legend, because those are what the parser has to skip.
ENCODERS_OUTPUT = """Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ..S... = Slice-level multithreading
 ------
 V....D a64multi             Multicolor charset for Commodore 64
 V....D prores_ks            Apple ProRes (iCodec Pro)
 V....D dnxhd                VC3/DNxHD
 A....D aac                  AAC (Advanced Audio Coding)
 S....D srt                  SubRip subtitle
"""


# --- ENCODER PARSING ---


def test_parse_encoders_finds_real_encoders():
    """Encoder names are pulled out of the table rows."""
    names = MediaToolchain.parse_encoders(ENCODERS_OUTPUT)

    assert "prores_ks" in names, "prores_ks is a table row and must be found"
    assert "dnxhd" in names
    assert "aac" in names


def test_parse_encoders_skips_legend_and_headings():
    """
    The flag legend must not be mistaken for encoders.

    Legend lines like ' V..... = Video' have a six character flag block in the
    first field, so they pass the shape test and have to be excluded by name.
    """
    names = MediaToolchain.parse_encoders(ENCODERS_OUTPUT)

    assert "=" not in names, "the flag legend was parsed as an encoder"
    assert "Video" not in names
    assert "Encoders:" not in names
    assert "------" not in names


def test_parse_encoders_handles_empty_output():
    """A build that fails to list encoders gives an empty set, not an error."""
    assert MediaToolchain.parse_encoders("") == set()


# --- DISCOVERY ---


def test_toolchain_can_skip_discovery():
    """discover=False leaves the tools unset, for tests that set them by hand."""
    toolchain = MediaToolchain(discover=False)

    assert toolchain.ffmpeg is None
    assert toolchain.ffprobe is None
    assert toolchain.is_ready is False


def test_versions_reports_missing_tools():
    """The sidecar's environment block records absence rather than crashing."""
    versions = MediaToolchain(discover=False).versions()

    assert versions["ffmpeg"] == "not found"
    assert versions["ffprobe"] == "not found"


def test_encoders_empty_without_ffmpeg():
    """Asking for encoders with no ffmpeg gives an empty set, not an exception."""
    assert MediaToolchain(discover=False).available_encoders() == set()


# --- FILTER PARSING ---

# Trimmed from real `ffmpeg -filters` output. The flag block is three characters
# here rather than the encoder table's six, which is the only structural
# difference between the two.
FILTERS_OUTPUT = """Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
  A = Audio input/output
  V = Video input/output
  ... abench            A->A       Benchmark part of a filtergraph.
  T.C drawtext          V->V       Draw text on top of video.
  ..C scale             V->V       Scale the input video size.
  ... concat            N->N       Concatenate audio and video streams.
"""


def test_parse_filters_finds_real_filters():
    names = MediaToolchain.parse_filters(FILTERS_OUTPUT)

    assert "drawtext" in names
    assert "scale" in names
    assert "concat" in names


def test_parse_filters_skips_legend_and_headings():
    """
    Same trap as the encoder legend, one field narrower.

    ' T.. = Timeline support' has a three character flag block and so passes
    the shape test, exactly as ' V..... = Video' does in the encoder table.
    """
    names = MediaToolchain.parse_filters(FILTERS_OUTPUT)

    assert "=" not in names, "the flag legend was parsed as a filter"
    assert "Filters:" not in names
    assert "input/output" not in names


def test_parse_filters_handles_empty_output():
    assert MediaToolchain.parse_filters("") == set()


def test_filters_are_empty_without_ffmpeg():
    """
    The state on a machine with no ffmpeg at all.

    Empty rather than raising, so the environment panel can report every row
    instead of failing on the first one.
    """
    assert MediaToolchain(discover=False).available_filters() == set()
    assert not MediaToolchain(discover=False).has_filter("drawtext")
