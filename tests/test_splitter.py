"""
Tests for Shot Extraction.

The frame-accuracy promise lives here, so the cases that matter are the ones a
thumbnail would never reveal: a shot one frame long or short, or a shot whose
pixels are not the pixels that were asked for.
"""

from pathlib import Path

import pytest

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo
from src.media.mezzanine import MezzanineBuilder
from src.media.probe import SourceProbe
from src.media.splitter import ShotSplitter

# --- FIXTURES ---


def make_splitter(source_path: str, output_dir: Path) -> ShotSplitter:
    source = SourceInfo(
        path=source_path,
        width=1920,
        height=1080,
        fps_numerator=24,
        fps_denominator=1,
        frame_count=1440,
        codec="h264",
    )
    return ShotSplitter(MediaToolchain(discover=False), Path("mezz.mp4"), source, output_dir)


@pytest.fixture
def splitter(tmp_path):
    return make_splitter("D:/cuts/CHAS_006_hatem_Edit_E_v02.mp4", tmp_path)


def shot(index: int) -> Shot:
    return Shot(index=index, start_frame=0, end_frame=23)


# --- NAMING ---


def test_shot_is_named_after_the_mini_cut(splitter):
    """
    Splitting two cuts into one directory must not have the second overwrite
    the first, so the source name is part of every shot filename.
    """
    assert splitter.filename_for(shot(7)) == "CHAS_006_hatem_Edit_E_v02_shot_007.mp4"


def test_shot_numbers_are_zero_padded(splitter):
    """Padding keeps shots in order in every file browser."""
    assert splitter.filename_for(shot(1)).endswith("_shot_001.mp4")
    assert splitter.filename_for(shot(42)).endswith("_shot_042.mp4")


def test_numbers_past_the_padding_still_work(splitter):
    """A thousand-shot cut widens the number rather than truncating it."""
    assert splitter.filename_for(shot(1234)).endswith("_shot_1234.mp4")


def test_container_follows_the_source(tmp_path):
    """Shots keep the source's container, because they keep its codec."""
    mov = make_splitter("D:/cuts/reel.mov", tmp_path)

    assert mov.filename_for(shot(1)) == "reel_shot_001.mov"


def test_missing_extension_falls_back_to_mp4(tmp_path):
    """A source with no extension still produces a playable filename."""
    odd = make_splitter("D:/cuts/reel", tmp_path)

    assert odd.filename_for(shot(1)) == "reel_shot_001.mp4"


# --- CUTTING (needs ffmpeg) ---


def frame_hashes(toolchain, path, start_seconds=None, duration_seconds=None) -> list:
    """
    Per-frame checksums of the decoded picture.

    Used to prove a cut contains the very same pixels as the span it came from,
    which a frame count alone cannot show.
    """
    arguments = ["-v", "error"]
    if start_seconds is not None:
        arguments += ["-ss", f"{start_seconds:.6f}"]
    arguments += ["-i", str(path)]
    if duration_seconds is not None:
        arguments += ["-t", f"{duration_seconds:.6f}"]
    arguments += ["-map", "0:v:0", "-an", "-c:v", "rawvideo", "-f", "framemd5", "-"]

    result = toolchain.run_ffmpeg(arguments, timeout=300.0)
    return [
        line.split(",")[-1].strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("#")
    ]


@pytest.fixture
def cut_setup(toolchain, clips, tmp_path):
    """A built mezzanine plus a splitter pointed at it, for the 25 fps clip."""
    source = SourceProbe(toolchain).probe(clips["pal"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mov")
    splitter = ShotSplitter(toolchain, mezzanine, source, tmp_path / "shots")
    return source, mezzanine, splitter


def test_a_shot_has_exactly_the_frames_asked_for(toolchain, cut_setup):
    """Frames 10 to 29 inclusive is 20 frames — not 19, not 21."""
    _, _, splitter = cut_setup

    written = splitter.extract(Shot(index=1, start_frame=10, end_frame=29))

    assert SourceProbe(toolchain).probe(written).frame_count == 20


def test_a_single_frame_shot(toolchain, cut_setup):
    """The shortest legitimate shot still has to come out at one frame."""
    _, _, splitter = cut_setup

    written = splitter.extract(Shot(index=1, start_frame=17, end_frame=17))

    assert SourceProbe(toolchain).probe(written).frame_count == 1


def test_the_cut_contains_the_right_pixels(toolchain, cut_setup):
    """
    The frames written are the frames requested, not merely the right number.

    A shot of the correct length taken from the wrong place would pass every
    other check in the project.
    """
    source, mezzanine, splitter = cut_setup

    written = splitter.extract(Shot(index=1, start_frame=10, end_frame=29))

    from_shot = frame_hashes(toolchain, written)
    from_mezzanine = frame_hashes(toolchain, mezzanine, start_seconds=10 / 25, duration_seconds=20 / 25)

    assert len(from_shot) == 20
    assert from_shot == from_mezzanine, "the cut is not the span it claims to be"


def test_a_shot_at_the_very_start(toolchain, cut_setup):
    """Frame 0 is a boundary case for seeking, so it is cut explicitly."""
    _, _, splitter = cut_setup

    written = splitter.extract(Shot(index=1, start_frame=0, end_frame=9))

    assert SourceProbe(toolchain).probe(written).frame_count == 10


def test_a_shot_running_to_the_last_frame(toolchain, cut_setup):
    """The tail of the source must not come up short."""
    source, _, splitter = cut_setup

    written = splitter.extract(
        Shot(index=1, start_frame=source.frame_count - 10, end_frame=source.frame_count - 1)
    )

    assert SourceProbe(toolchain).probe(written).frame_count == 10


def test_extract_all_writes_every_shot_and_records_the_paths(toolchain, cut_setup):
    source, _, splitter = cut_setup
    shots = [
        Shot(index=1, start_frame=0, end_frame=19),
        Shot(index=2, start_frame=20, end_frame=39),
        Shot(index=3, start_frame=40, end_frame=49),
    ]

    written = splitter.extract_all(shots)

    assert [Path(shot.file).name for shot in written] == [
        "pal_shot_001.mov",
        "pal_shot_002.mov",
        "pal_shot_003.mov",
    ]
    for shot in written:
        assert Path(shot.file).is_file()
        assert SourceProbe(toolchain).probe(Path(shot.file)).frame_count == shot.frame_count


def test_the_shots_together_account_for_every_source_frame(toolchain, cut_setup):
    """The whole point: split the source and lose nothing."""
    source, _, splitter = cut_setup
    shots = [
        Shot(index=1, start_frame=0, end_frame=19),
        Shot(index=2, start_frame=20, end_frame=49),
    ]

    written = splitter.extract_all(shots)
    total = sum(SourceProbe(toolchain).probe(Path(shot.file)).frame_count for shot in written)

    assert total == source.frame_count


def test_h265_cuts_as_exactly_as_h264(toolchain, clips, tmp_path):
    """
    h265 is expected material, and x265 handles keyframes differently, so its
    accuracy is proven rather than assumed.

    Same assertion as the h264 case: the frames written are the frames asked
    for, and they are the right pixels.
    """
    source = SourceProbe(toolchain).probe(clips["h265"])
    assert source.codec == "hevc"

    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mp4")
    splitter = ShotSplitter(toolchain, mezzanine, source, tmp_path / "shots")

    written = splitter.extract(Shot(index=1, start_frame=10, end_frame=29))
    result = SourceProbe(toolchain).probe(written)

    assert result.codec == "hevc", "shots come back in the codec they went in as"
    assert result.frame_count == 20

    from_shot = frame_hashes(toolchain, written)
    from_mezzanine = frame_hashes(
        toolchain, mezzanine, start_seconds=10 / 24, duration_seconds=20 / 24
    )
    assert from_shot == from_mezzanine


def test_h265_shots_tile_the_source(toolchain, clips, tmp_path):
    """Splitting an h265 source loses no frames either."""
    source = SourceProbe(toolchain).probe(clips["h265"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mp4")
    splitter = ShotSplitter(toolchain, mezzanine, source, tmp_path / "shots")

    shots = [
        Shot(index=1, start_frame=0, end_frame=17),
        Shot(index=2, start_frame=18, end_frame=source.frame_count - 1),
    ]
    written = splitter.extract_all(shots)

    total = sum(SourceProbe(toolchain).probe(Path(shot.file)).frame_count for shot in written)
    assert total == source.frame_count


def test_audio_is_carried_into_the_shots(toolchain, clips, tmp_path):
    """Mini cuts have sound, and a silent shot file is no use for review."""
    source = SourceProbe(toolchain).probe(clips["with_audio"])
    mezzanine = MezzanineBuilder(toolchain).build(source, tmp_path / "mezz.mp4")
    splitter = ShotSplitter(toolchain, mezzanine, source, tmp_path / "shots")

    written = splitter.extract(Shot(index=1, start_frame=0, end_frame=23))

    result = toolchain.run_ffprobe(
        ["-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(written)],
        timeout=60.0,
    )
    assert "audio" in result.stdout
