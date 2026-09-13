"""
Tests for Reading Production Knowledge.

The file is a show's own markdown, written by a person and read by a model, so
nothing here parses its meaning. What is tested is finding it and counting what
is in it — the cases where a file is plainly there and the app says it is not
are the ones that waste somebody's afternoon.
"""

from pathlib import Path

import pytest

from src.identifier.knowledge import PRODUCTION_FILE, count_entries, load_knowledge
from src.identifier.templates import FILM_TERMINOLOGY

# --- FINDING THE FILE ---


def test_the_production_file_is_read_from_the_folder(tmp_path):
    (tmp_path / PRODUCTION_FILE).write_text(
        "# Characters\n\n## Tess\nBlue hair.\n", encoding="utf-8"
    )

    knowledge = load_knowledge(tmp_path)

    assert knowledge.has_production
    assert "Blue hair" in knowledge.production


def test_terminology_ships_with_the_app_and_is_always_there():
    """
    Film terminology changes almost never, so it is not the user's file and is
    never shown to them.

    Keeping it out of the production folder means nobody edits the one thing
    here that does not need editing — and a terminology file quietly broken is
    a whole batch described in words that match no shot list.
    """
    knowledge = load_knowledge(Path("no-such-folder"))

    assert knowledge.has_terminology
    assert knowledge.terminology == FILM_TERMINOLOGY
    assert "OTS" in knowledge.terminology
    assert "dolly zoom" in knowledge.terminology.lower()


def test_a_missing_folder_is_not_an_error(tmp_path):
    """
    The state on a fresh install, before anyone has written anything.

    Without it the tab still describes every shot, in plain words, with nobody
    named — a reduced result rather than a failure, and exactly what a
    breakdown for a show with no list yet wants.
    """
    knowledge = load_knowledge(tmp_path / "not-created-yet")

    assert not knowledge.has_production
    assert knowledge.has_terminology, "terminology ships with the app"


def test_the_name_is_matched_whatever_its_case(tmp_path):
    """
    Windows and macOS are case-insensitive; Linux is not.

    A file saved as `Production.md` works on the machine it was written on and
    silently stops working when the project moves, which is the worst kind of
    bug to chase.
    """
    (tmp_path / "Production.MD").write_text("# Characters\n", encoding="utf-8")

    assert load_knowledge(tmp_path).has_production


def test_a_file_written_by_a_windows_editor_still_reads(tmp_path):
    """
    This is a hand-written file, so sooner or later it arrives with a byte
    order mark on the front of it.
    """
    (tmp_path / PRODUCTION_FILE).write_bytes(b"\xef\xbb\xbf# Characters\n\n## Tess\n")

    knowledge = load_knowledge(tmp_path)

    assert knowledge.production.startswith("# Characters"), "no stray BOM in the text"
    assert knowledge.counts["characters"] == 1


def test_a_file_where_the_folder_should_be_is_refused(tmp_path):
    """A path typed wrong should say so, not behave as though the show had no knowledge."""
    target = tmp_path / "notafolder.md"
    target.write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        load_knowledge(target)


# --- COUNTING WHAT IS IN IT ---


def test_entries_are_counted_under_each_category():
    """
    The panel says "3 characters, 2 props" so someone can see at a glance that
    the file was read the way they meant it.
    """
    counts = count_entries(
        "# Characters\n## Tess\n## Marcus\n## Nell\n"
        "# Props\n## The radio\n## A backpack\n"
        "# Environments\n## The shoreline\n"
    )

    assert counts == {"characters": 3, "props": 2, "environments": 1}


def test_a_category_with_nothing_in_it_counts_zero():
    """
    Which is what a heading typed at the wrong level looks like.

    `# Tess` under `# Characters` opens a second category rather than adding an
    entry, so the count drops to zero and the panel shows it — this count
    exists to make exactly that visible.
    """
    counts = count_entries("# Characters\n# Tess\nBlue hair.\n")

    assert counts["characters"] == 0


def test_a_category_that_is_absent_is_absent_rather_than_zero():
    """
    "No props section" and "a props section with nothing in it" are different
    things, and only the second is worth mentioning to the user.
    """
    counts = count_entries("# Characters\n## Tess\n")

    assert "props" not in counts
    assert counts == {"characters": 1}


def test_headings_are_matched_whatever_their_case():
    """A person writing markdown will not think about this, and should not have to."""
    assert count_entries("# CHARACTERS\n## Tess\n") == {"characters": 1}


def test_an_unknown_category_is_ignored_rather_than_refused():
    """
    Everything in the file still reaches the model; only the counts are
    restricted to the categories the panel knows how to report.
    """
    counts = count_entries("# Characters\n## Tess\n# Vehicles\n## The van\n")

    assert counts == {"characters": 1}


def test_an_empty_file_counts_nothing():
    assert count_entries("") == {}
