"""
Project Knowledge.

What the interpretation pass reads, and the reason the vocabulary in this tab
belongs to the project rather than to whichever model answered.

Two kinds of knowledge, deliberately kept apart because they change at
completely different rates:

**The production's own** — `characters.md` in the production folder beside the
app. Who is in the show, and *how each one appears in different
representations*: what they look like in a final render, and that in a CG
blockout they are a particular mannequin. That cross-representation note is
what lets a red mannequin on rollerskates be recognised as the same character
as a woman with blue hair. This changes every job, so it is the user's file, in
a folder they own, read on every run.

**Film terminology** — `templates.FILM_TERMINOLOGY`, shipped with the app. What
CS and OTS and "dolly in" mean. This changes almost never, so it is deliberately
not sitting next to the character sheet: exposing it there invites editing the
one thing that does not need editing, and a terminology file quietly broken is
a whole batch described in words that match no shot list.

Props and environments will follow the production pattern later, and are
deliberately not built now.

The character sheet lives in a directory rather than being uploaded each
session: it is written once and then read on every run, and making someone
attach it every time would guarantee it gets skipped.
"""

import logging
from pathlib import Path

from src.core.models import ProjectKnowledge
from src.identifier.templates import FILM_TERMINOLOGY

# --- FILE NAMES ---

# Only the production's own files are named here. Terminology ships with the
# app and has no path.
CHARACTERS_FILE = "characters.md"


def load_knowledge(directory: Path) -> ProjectKnowledge:
    """
    Reads whichever knowledge files are present in a directory.

    Terminology always comes back, because it ships with the app. Only the
    production's own files are looked for on disk.

    Args:
        directory: The production folder holding the character sheet.

    Returns:
        ProjectKnowledge: terminology always, and the character sheet if it is
        there. A missing character sheet is not a failure — the tab still
        describes every shot, it just describes them without naming anyone,
        which is how the breakdown export is meant to be used on a show that
        has no character list yet.

    Raises:
        NotADirectoryError: If the path exists but is not a directory. A path
            typed wrong should say so rather than silently behave as though the
            project had no knowledge at all.

    Notes:
        A directory that does not exist yet is not an error — it is the state
        on a fresh install, before anyone has put a character sheet in it.
        Empty knowledge comes back and the tab says so.
    """
    if not directory.exists():
        return ProjectKnowledge(directory=str(directory), terminology=FILM_TERMINOLOGY)

    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    return ProjectKnowledge(
        directory=str(directory),
        terminology=FILM_TERMINOLOGY,
        characters=_read(directory, CHARACTERS_FILE),
    )


def _read(directory: Path, name: str) -> str:
    """
    Reads one knowledge file, matching its name case-insensitively.

    Notes:
        Windows is case-insensitive and macOS usually is, so a file saved as
        `Characters.md` works on the machine it was written on and quietly
        stops working when the project moves to Linux. Matching on the lowered
        name means it behaves the same everywhere.

        Read as utf-8-sig: these are hand-written files, and a Windows editor
        will have left a byte order mark on the front of at least one of them.
    """
    for path in directory.iterdir():
        if path.is_file() and path.name.lower() == name:
            try:
                return path.read_text(encoding="utf-8-sig")
            except OSError as error:
                logging.warning(f"Could not read {path}: {error}")
                return ""

    return ""
