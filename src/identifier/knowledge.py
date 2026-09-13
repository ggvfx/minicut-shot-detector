"""
Project Knowledge.

What the interpretation pass reads, and the reason the vocabulary in this tab
belongs to the project rather than to whichever model answered.

Two kinds of knowledge, deliberately kept apart because they change at
completely different rates:

**The production's own** — `production.md` in a folder beside the app. Who and
what is in the show, and *how each appears in different representations*: what
a character looks like in a final render, and that in a CG blockout they are a
particular mannequin. That cross-representation note is what lets a red
mannequin on rollerskates be recognised as the same character as a woman with
blue hair. This changes every job, so it is the user's file, read on every run.

**Film terminology** — `templates.FILM_TERMINOLOGY`, shipped with the app and
never shown. What CS and OTS and "dolly in" mean changes almost never, so
putting it in front of the user would only invite editing the one thing that
does not need editing.

The production file lives in a directory rather than being uploaded each
session: it is written once and then read on every run, and making someone
attach it every time would guarantee it gets skipped.
"""

import logging
import re
from pathlib import Path
from typing import Dict

from src.core.models import ProjectKnowledge
from src.identifier.templates import FILM_TERMINOLOGY

# --- THE FILE ---

PRODUCTION_FILE = "production.md"

# --- CATEGORIES ---

# The top-level headings the file is organised under, and the order the panel
# reports them in. Anything under another heading is still read and still sent
# to the model — these only decide what gets counted back to the user.
CATEGORIES = ("characters", "props", "environments")

# A level-one heading opens a category; a level-two heading is one entry in it.
# Counting entries is what lets the panel say "20 characters, 5 props", which
# is the cheapest way for someone to see the file was read the way they meant.
CATEGORY_HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
ENTRY_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def load_knowledge(directory: Path) -> ProjectKnowledge:
    """
    Reads the production file, and attaches the shipped terminology.

    Terminology always comes back, because it ships with the app. Only the
    production's own file is looked for on disk.

    Args:
        directory: The production folder.

    Returns:
        ProjectKnowledge: terminology always, the production file if it is
        there, and a count of the entries under each category. A missing file
        is not a failure — the tab still describes every shot, it just does so
        without naming anyone, which is how the breakdown export is meant to be
        used on a show that has no character list yet.

    Raises:
        NotADirectoryError: If the path exists but is not a directory. A path
            typed wrong should say so rather than silently behave as though the
            project had no knowledge at all.
    """
    if not directory.exists():
        return ProjectKnowledge(directory=str(directory), terminology=FILM_TERMINOLOGY)

    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    production = _read(directory, PRODUCTION_FILE)

    return ProjectKnowledge(
        directory=str(directory),
        terminology=FILM_TERMINOLOGY,
        production=production,
        counts=count_entries(production),
    )


def count_entries(markdown: str) -> Dict[str, int]:
    """
    How many entries sit under each category heading.

    Args:
        markdown: The production file's text.

    Returns:
        One count per category found, keyed by the lowered heading. Categories
        absent from the file are absent here rather than zero — "no props
        section" and "a props section with nothing in it" are different things,
        and only the second is worth mentioning.

    Notes:
        Counted by heading level: `# Characters` opens a category and each
        `## Tess` under it is one entry. Getting that wrong is the mistake this
        count exists to reveal — a heading typed at the wrong level shows up as
        a category with no entries, which is visible at a glance in the panel.
    """
    counts: Dict[str, int] = {}

    # Split on the category headings, keeping what follows each one. The first
    # piece is whatever preceded the first heading and is not a category.
    sections = CATEGORY_HEADING.split(markdown)

    for name, body in zip(sections[1::2], sections[2::2]):
        key = name.strip().lower()
        if key in CATEGORIES:
            counts[key] = len(ENTRY_HEADING.findall(body))

    return counts


def _read(directory: Path, name: str) -> str:
    """
    Reads one file, matching its name case-insensitively.

    Notes:
        Windows is case-insensitive and macOS usually is, so a file saved as
        `Production.md` works on the machine it was written on and quietly
        stops working when the project moves to Linux. Matching on the lowered
        name means it behaves the same everywhere.

        Read as utf-8-sig: this is a hand-written file, and a Windows editor
        will have left a byte order mark on the front of it.
    """
    for path in directory.iterdir():
        if path.is_file() and path.name.lower() == name:
            try:
                return path.read_text(encoding="utf-8-sig")
            except OSError as error:
                logging.warning(f"Could not read {path}: {error}")
                return ""

    return ""
