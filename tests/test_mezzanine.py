"""
Tests for Mezzanine Encoder Selection.

The encoding arguments are pure logic, so they are tested without running an
encode. What they produce was verified by hand first: cutting 30 frames out of
an all-intra h264 mezzanine yields exactly 30 frames, pixel-identical to the
same span of the mezzanine.
"""

import pytest

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import SourceInfo
from src.media.mezzanine import MezzanineBuilder

# --- FIXTURES ---


@pytest.fixture
def builder():
    return MezzanineBuilder(MediaToolchain(discover=False))


def make_source(**overrides) -> SourceInfo:
    fields = {
        "path": "reel.mp4",
        "width": 1920,
        "height": 1080,
        "fps_numerator": 24,
        "fps_denominator": 1,
        "frame_count": 1440,
        "codec": "h264",
    }
    fields.update(overrides)
    return SourceInfo(**fields)


# --- ENCODER SELECTION ---


def test_h264_source_gets_libx264(builder):
    """Shots come out in the codec they went in as."""
    assert builder.encoder_for(make_source(codec="h264")) == "libx264"


def test_h265_source_gets_libx265(builder):
    """ffprobe calls h265 "hevc", which is what the mapping has to key on."""
    assert builder.encoder_for(make_source(codec="hevc")) == "libx265"


def test_unsupported_codec_is_refused(builder):
    """
    Better to refuse than to hand back shots in a different format.

    Re-encoding a ProRes source to h264 would change what the user gave us,
    which is exactly what this tool must not do.
    """
    with pytest.raises(ValueError, match="prores"):
        builder.encoder_for(make_source(codec="prores"))


# --- ENCODING ARGUMENTS ---


def test_every_frame_is_a_keyframe_for_h264(builder):
    """
    Without this the whole approach collapses: a stream copy can only cut on a
    keyframe, so a long-GOP mezzanine would move boundaries by seconds.
    """
    arguments = builder.arguments_for(make_source(codec="h264"))

    assert "-g" in arguments
    assert arguments[arguments.index("-g") + 1] == "1"


def test_every_frame_is_a_keyframe_for_h265(builder):
    """x265 takes its keyframe interval through -x265-params, not -g."""
    arguments = builder.arguments_for(make_source(codec="hevc"))

    assert "-x265-params" in arguments
    assert "keyint=1" in arguments[arguments.index("-x265-params") + 1]


def test_pixel_format_is_carried_across(builder):
    """A 10-bit source must not be quietly flattened to 8-bit on the way out."""
    arguments = builder.arguments_for(make_source(pixel_format="yuv420p10le"))

    assert arguments[arguments.index("-pix_fmt") + 1] == "yuv420p10le"


def test_no_crop_filter_is_ever_applied(builder):
    """
    Detected letterboxing describes the source; it is not an instruction to
    reshape it. The shots handed back must be the shots given to us.
    """
    arguments = builder.arguments_for(make_source(detected_crop="1920:800:0:140"))

    assert "-vf" not in arguments
    assert not any("crop" in argument for argument in arguments)
