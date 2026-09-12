"""
Tests for Shot File Naming.

The cutting itself arrives in task 3.3; naming is testable now and is what
stops two mini cuts overwriting each other in a shared output directory.
"""

from pathlib import Path

import pytest

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Shot, SourceInfo
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
