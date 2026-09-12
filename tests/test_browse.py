"""
Tests for the Path Picker Listing.

Everything runs against a temporary directory, so there is no dependency on
what happens to be on the developer's disk.
"""

import pytest

from src.ui.browse import available_roots, list_directory


# --- FIXTURE ---


@pytest.fixture
def sample_tree(tmp_path):
    """A directory holding one subfolder, one video and one non-video file."""
    (tmp_path / "shots").mkdir()
    (tmp_path / "reel_01.mov").write_bytes(b"not really a movie")
    (tmp_path / "notes.txt").write_text("just a text file")
    return tmp_path


# --- LISTING ---


def test_directories_come_before_files(sample_tree):
    """Folders sort to the top so the picker reads like a file browser."""
    listing = list_directory(sample_tree)

    assert listing.entries[0].is_directory is True
    assert listing.entries[0].name == "shots"
    assert [entry.name for entry in listing.entries[1:]] == ["notes.txt", "reel_01.mov"]


def test_videos_are_flagged(sample_tree):
    """Recognised video extensions are marked, so the UI can style them."""
    entries = {entry.name: entry for entry in list_directory(sample_tree).entries}

    assert entries["reel_01.mov"].is_video is True
    assert entries["notes.txt"].is_video is False


def test_videos_only_hides_other_files(sample_tree):
    """The source picker hides anything that is not video, but keeps folders."""
    names = [entry.name for entry in list_directory(sample_tree, videos_only=True).entries]

    assert "reel_01.mov" in names
    assert "notes.txt" not in names
    assert "shots" in names, "folders must stay visible or you cannot navigate"


def test_file_size_is_reported(sample_tree):
    """Size is shown so a truncated or empty file is obvious before a job."""
    entries = {entry.name: entry for entry in list_directory(sample_tree).entries}

    assert entries["reel_01.mov"].size_bytes == len(b"not really a movie")


# --- NAVIGATION ---


def test_parent_is_set_for_a_nested_directory(sample_tree):
    """A nested directory offers a way back up."""
    listing = list_directory(sample_tree / "shots")

    assert listing.parent == str(sample_tree)


def test_roots_are_offered(sample_tree):
    """Drive shortcuts are always available, whatever directory is shown."""
    listing = list_directory(sample_tree)

    assert listing.roots == available_roots()
    assert len(listing.roots) >= 1


def test_listing_a_file_raises(sample_tree):
    """Pointing the picker at a file is an error, not an empty listing."""
    with pytest.raises(NotADirectoryError):
        list_directory(sample_tree / "reel_01.mov")
