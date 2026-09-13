"""
Project Knowledge.

The markdown files a production supplies, and the reason the vocabulary in this
tab belongs to the project rather than to whichever model answered.

Two files to begin with, both plain markdown so they can live in a show's repo,
be reviewed, and be edited by someone who does not write code:

**terminology.md** — how this facility names things. "Top of head to shoulders"
is a CS here and a BCU somewhere else, and both are correct. Holding it in a
file the user owns is what makes the same observation produce the same term on
every shot of a batch.

**characters.md** — who is in the show, in detail, and *how each one appears in
different representations*: what they look like in a final render, and that in
a CG blockout they are a particular mannequin. That cross-representation note
is what lets a red mannequin on rollerskates be recognised as the same
character as a woman with blue hair.

Props and environments are expected to follow the same pattern later, and are
deliberately not built now.

The files live in a directory beside the app rather than being uploaded each
session: a show's character sheet is written once and then read on every run,
and making someone attach it every time would guarantee it gets skipped.
"""

import logging
from pathlib import Path

from src.core.models import ProjectKnowledge

# --- FILE NAMES ---

TERMINOLOGY_FILE = "terminology.md"
CHARACTERS_FILE = "characters.md"


def load_knowledge(directory: Path) -> ProjectKnowledge:
    """
    Reads whichever knowledge files are present in a directory.

    Args:
        directory: A project folder holding the markdown files.

    Returns:
        ProjectKnowledge: with whatever was found. Both files are optional —
        without them the tab still describes every shot, it just describes them
        in plain words and does not name anyone. That is a reduced result
        rather than a failure, and is how the breakdown export is expected to
        be used on a show that has no character sheet yet.

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
        return ProjectKnowledge(directory=str(directory))

    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    return ProjectKnowledge(
        directory=str(directory),
        terminology=_read(directory, TERMINOLOGY_FILE),
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
