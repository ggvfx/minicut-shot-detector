"""
Tests for Reading Production Knowledge.

The files are a show's own markdown, written by a person and read by a model,
so nothing here parses them. What is tested is finding them: the cases where a
file is plainly there and the app says it is not are the ones that waste
somebody's afternoon.
"""
from pathlib import Path

import pytest

from src.identifier.knowledge import CHARACTERS_FILE, load_knowledge
from src.identifier.templates import FILM_TERMINOLOGY


def test_the_character_sheet_is_read_from_the_folder(tmp_path):
    (tmp_path / CHARACTERS_FILE).write_text("# Characters\nTess has blue hair.", encoding="utf-8")

    knowledge = load_knowledge(tmp_path)

    assert knowledge.has_characters
    assert "blue hair" in knowledge.characters


def test_terminology_ships_with_the_app_and_is_always_there():
    """
    Film terminology changes almost never, so it is not the user's file.

    Keeping it out of the production folder means nobody edits the one thing
    here that does not need editing — and a terminology file quietly broken is
    a whole batch described in words that match no shot list.
    """
    knowledge = load_knowledge(Path("no-such-folder"))

    assert knowledge.has_terminology
    assert knowledge.terminology == FILM_TERMINOLOGY
    assert "OTS" in knowledge.terminology


def test_a_missing_folder_is_not_an_error(tmp_path):
    """
    The state on a fresh install, before anyone has put a sheet in it.

    Without knowledge the tab still describes every shot, in plain words, with
    nobody named — a reduced result rather than a failure, and exactly what a
    breakdown for a show with no character list yet wants.
    """
    knowledge = load_knowledge(tmp_path / "not-created-yet")

    assert not knowledge.has_characters
    assert knowledge.has_terminology, "terminology ships with the app"


def test_the_name_is_matched_whatever_its_case(tmp_path):
    """
    Windows and macOS are case-insensitive; Linux is not.

    A sheet saved as `Characters.md` works on the machine it was written on and
    silently stops working when the project moves, which is the worst kind of
    bug to chase.
    """
    (tmp_path / "Characters.MD").write_text("# Characters", encoding="utf-8")

    assert load_knowledge(tmp_path).has_characters


def test_a_file_written_by_a_windows_editor_still_reads(tmp_path):
    """
    These are hand-written files, so at least one will arrive with a byte order
    mark on the front of it.
    """
    (tmp_path / CHARACTERS_FILE).write_bytes(b"\xef\xbb\xbf# Characters\nTess.")

    knowledge = load_knowledge(tmp_path)

    assert knowledge.characters.startswith("# Characters"), "no stray BOM in the text"


def test_a_file_where_the_folder_should_be_is_refused(tmp_path):
    """A path typed wrong should say so, not behave as though the show had no knowledge."""
    target = tmp_path / "notafolder.md"
    target.write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        load_knowledge(target)
