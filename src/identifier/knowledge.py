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

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

# --- FILE NAMES ---

TERMINOLOGY_FILE = "terminology.md"
CHARACTERS_FILE = "characters.md"


class ProjectKnowledge(BaseModel):
    """
    The markdown a project supplies, as text.

    Held as text rather than parsed into structure. These files are written by
    people for a model to read, and the moment we impose a schema on them we
    are asking a production to fill in our form instead of describing their
    show. The interpret pass gets them as they are.

    Attributes:
        terminology: How this project names shot sizes, types and moves.
        characters: Who is in it and how they appear in each representation.
        directory: Where they came from, for the UI to show.
    """

    terminology: str = ""
    characters: str = ""
    directory: Optional[str] = None

    @property
    def has_terminology(self) -> bool:
        """Whether terms can be applied, or observations stay in plain words."""
        return bool(self.terminology.strip())

    @property
    def has_characters(self) -> bool:
        """Whether appearances can be named, or stay as descriptions."""
        return bool(self.characters.strip())


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
        NotADirectoryError: If the path is not a directory. A path typed wrong
            should say so rather than silently behave as though the project had
            no knowledge at all.
    """
    # PSEUDOCODE
    # 1. Refuse anything that is not a directory.
    # 2. Read each known file if present, ignoring case in the name.
    # 3. Return ProjectKnowledge with whatever was found.
    raise NotImplementedError
