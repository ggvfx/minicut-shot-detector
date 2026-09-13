"""
Tests for the Working Folder.

Every case here is about which files may be deleted and which must not. The
mezzanine of the source being reviewed is what the split cuts from, so getting
this wrong takes away the thing the next step needs.

No ffmpeg and no real media: the rules are about names and sizes, so the files
are written as bytes and the tests run in milliseconds.
"""

from pathlib import Path

from src.media.workspace import WORK_DIRECTORY, clear_work, reclaimable_work

# --- HELPERS ---

def work_file(output_dir: Path, name: str, size: int = 1024) -> Path:
    """A file of a given size in the work folder, as an analysis would leave."""
    work_dir = output_dir / WORK_DIRECTORY
    work_dir.mkdir(exist_ok=True)

    path = work_dir / name
    path.write_bytes(b"\0" * size)
    return path


def test_nothing_is_reclaimable_without_a_work_folder(tmp_path):
    """An output directory nothing has run in yet has nothing to clear."""
    assert reclaimable_work(tmp_path) == []


def test_everything_is_reclaimable_when_no_source_is_open(tmp_path):
    """
    Before anything is analysed, every leftover is fair game.

    This is the case the button exists for: files left by a session that was
    closed without splitting.
    """
    work_file(tmp_path, "reel_01_mezzanine.mp4")
    work_file(tmp_path, "reel_01_proxy.mp4")

    assert len(reclaimable_work(tmp_path)) == 2


def test_the_open_source_is_never_offered_up(tmp_path):
    """
    The mezzanine of the source being reviewed is what the split cuts from.

    Offering it for deletion would break the next step the user takes.
    """
    work_file(tmp_path, "reel_01_mezzanine.mp4")
    work_file(tmp_path, "reel_01_proxy.mp4")
    work_file(tmp_path, "reel_02_mezzanine.mp4")

    reclaimable = reclaimable_work(tmp_path, keep_source=Path("D:/media/reel_01.mp4"))

    assert [path.name for path in reclaimable] == ["reel_02_mezzanine.mp4"]


def test_a_longer_name_starting_with_the_open_one_is_still_reclaimable(tmp_path):
    """
    "reel_02" must not claim "reel_02_extra"'s files.

    Matching on a name prefix would spare the wrong mezzanine here and leave
    the user wondering why clearing freed less than it said it would.
    """
    work_file(tmp_path, "reel_02_mezzanine.mp4")
    work_file(tmp_path, "reel_02_extra_mezzanine.mp4")

    reclaimable = reclaimable_work(tmp_path, keep_source=Path("reel_02.mp4"))

    assert [path.name for path in reclaimable] == ["reel_02_extra_mezzanine.mp4"]


def test_clearing_reports_the_bytes_it_freed(tmp_path):
    """The figure shown to the user has to be what actually went."""
    work_file(tmp_path, "reel_01_mezzanine.mp4", size=4096)
    work_file(tmp_path, "reel_01_proxy.mp4", size=2048)

    assert clear_work(tmp_path) == 6144
    assert reclaimable_work(tmp_path) == []


def test_clearing_removes_the_work_folder_when_it_empties(tmp_path):
    """An output directory that is finished with should look finished with."""
    work_file(tmp_path, "reel_01_mezzanine.mp4")

    clear_work(tmp_path)

    assert not (tmp_path / WORK_DIRECTORY).exists()


def test_clearing_keeps_the_folder_while_the_open_source_needs_it(tmp_path):
    """The folder stays as long as anything is still using it."""
    work_file(tmp_path, "reel_01_mezzanine.mp4")
    work_file(tmp_path, "reel_02_mezzanine.mp4")

    clear_work(tmp_path, keep_source=Path("reel_01.mp4"))

    assert (tmp_path / WORK_DIRECTORY / "reel_01_mezzanine.mp4").is_file()


def test_round_trip_scratch_belongs_to_nobody_and_always_goes(tmp_path):
    """
    `concat.txt` and `rejoined.mp4` are named after no source.

    They must not be spared by whichever source happens to be open.
    """
    work_file(tmp_path, "concat.txt")
    work_file(tmp_path, "rejoined.mp4")

    reclaimable = reclaimable_work(tmp_path, keep_source=Path("reel_01.mp4"))

    assert len(reclaimable) == 2
