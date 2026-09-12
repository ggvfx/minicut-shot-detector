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
from src.media.probe import SourceProbe

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


# --- TIMEOUTS ---


def test_timeout_scales_with_source_length(builder):
    """
    A fixed timeout would either abandon a long job or let a hung one block
    the app for hours.
    """
    one_minute = builder._timeout_for(make_source(fps_numerator=24, frame_count=1440))
    ten_minutes = builder._timeout_for(make_source(fps_numerator=24, frame_count=14400))

    assert ten_minutes > one_minute
    assert one_minute >= 600, "short sources still get a sensible floor"


# --- BUILDING (needs ffmpeg) ---


def probe_frames(toolchain, path) -> int:
    return SourceProbe(toolchain).probe(path).frame_count


def keyframe_flags(toolchain, path) -> list:
    """Reads the key_frame flag of every video frame in a file."""
    result = toolchain.run_ffprobe(
        [
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "frame=key_frame",
            "-of", "csv=p=0",
            str(path),
        ],
        timeout=120.0,
    )
    return [line.strip().rstrip(",") for line in result.stdout.splitlines() if line.strip()]


def stream_types(toolchain, path) -> list:
    result = toolchain.run_ffprobe(
        ["-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        timeout=60.0,
    )
    return [line.strip().rstrip(",") for line in result.stdout.splitlines() if line.strip()]


def test_mezzanine_keeps_every_frame(toolchain, clips, tmp_path):
    """
    A mezzanine one frame short would shift every shot cut from it.

    This is the check that makes the rest of the pipeline trustworthy.
    """
    probe = SourceProbe(toolchain)
    source = probe.probe(clips["pal"])

    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mov")

    assert probe_frames(toolchain, mezzanine) == source.frame_count == 50


def test_every_frame_of_the_mezzanine_is_a_keyframe(toolchain, clips, tmp_path):
    """
    The whole approach rests on this: a stream copy can only cut on a keyframe.

    If even one frame is not a keyframe, a cut there silently lands elsewhere.
    """
    source = SourceProbe(toolchain).probe(clips["pal"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mov")

    flags = keyframe_flags(toolchain, mezzanine)

    assert len(flags) == 50
    assert set(flags) == {"1"}, "every frame must be a keyframe"


def test_audio_survives_the_mezzanine(toolchain, clips, tmp_path):
    """Mini cuts carry sound, and shots cut from this must keep it."""
    source = SourceProbe(toolchain).probe(clips["with_audio"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mp4")

    assert "audio" in stream_types(toolchain, mezzanine)


def test_a_silent_source_is_not_an_error(toolchain, clips, tmp_path):
    """Two of the six reference deliveries have no audio at all."""
    source = SourceProbe(toolchain).probe(clips["pal"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mov")

    assert "audio" not in stream_types(toolchain, mezzanine)


def test_h265_source_produces_an_all_intra_h265_mezzanine(toolchain, clips, tmp_path):
    """
    x265 takes its keyframe interval differently from x264, so this is proven
    rather than assumed — h265 material is expected.
    """
    source = SourceProbe(toolchain).probe(clips["h265"])
    assert source.codec == "hevc"

    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mp4")
    result = SourceProbe(toolchain).probe(mezzanine)

    assert result.codec == "hevc", "shots must come back in the codec they went in as"
    assert result.frame_count == source.frame_count
    assert set(keyframe_flags(toolchain, mezzanine)) == {"1"}


def test_pixel_format_survives(toolchain, clips, tmp_path):
    """A 10-bit source must not be quietly flattened on the way through."""
    source = SourceProbe(toolchain).probe(clips["pal"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mov")

    assert SourceProbe(toolchain).probe(mezzanine).pixel_format == source.pixel_format


# --- VERIFYING ---


def test_verify_rejects_a_mezzanine_of_the_wrong_source(toolchain, clips, tmp_path):
    """
    Verification compares against the source it claims to represent.

    Here a 25 fps mezzanine is checked against the 23.976 source, which is the
    shape of a mix-up that would otherwise be found frames at a time later.
    """
    probe = SourceProbe(toolchain)
    builder = MezzanineBuilder(toolchain)

    mezzanine = builder.build(probe.probe(clips["pal"]), tmp_path / "mezz.mov")
    wrong_source = probe.probe(clips["film"])

    assert builder.verify(wrong_source, mezzanine) is False


def test_verify_reports_a_missing_file(toolchain, tmp_path):
    builder = MezzanineBuilder(toolchain)

    assert builder.verify(make_source(), tmp_path / "never-written.mov") is False


def test_build_refuses_an_unsupported_codec(toolchain, tmp_path):
    """A ProRes source cannot be reproduced, so nothing is written."""
    with pytest.raises(ValueError, match="prores"):
        MezzanineBuilder(toolchain).build(make_source(codec="prores"), tmp_path / "mezz.mov")
