"""
Reading a Shot List.

Three sources, one destination. However a production hands over its shot list,
it ends as `ShotListEntry` records with a number and a description, and the
matching step never knows which kind it came from.

**CSV or TSV** — parsed properly, with the user confirming which column is the
shot number and which is the description. Columns are named differently at
every facility and guessing silently is how you match against the wrong field.

**A text document** — no reliable structure, so this is where the text backend
earns its keep: it normalises a messy document into number and description
pairs for a person to confirm. The deterministic path is tried first; a model
is the fallback, not the default.

**A folder of thumbnails named by shot number** — each image is described by
the vision pass and interpreted exactly like a video, so it becomes text and
joins the same matching engine. A still has no camera movement, which is why
entries carry `is_still`: matching must not penalise a reference for lacking an
attribute it could never have had.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from src.identifier.models import ShotListEntry

# --- RECOGNISED INPUT ---

TABLE_SUFFIXES = (".csv", ".tsv")
TEXT_SUFFIXES = (".txt", ".md")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")

# Column names seen often enough to offer as a default. Only ever a suggestion
# the user confirms — see the module docstring.
LIKELY_NUMBER_COLUMNS = ("shot", "shot_number", "shot number", "shot code", "code", "id")
LIKELY_DESCRIPTION_COLUMNS = ("description", "shot description", "notes", "action", "summary")


def read_table(path: Path, number_column: str, description_column: str) -> List[ShotListEntry]:
    """
    Reads a CSV or TSV using the columns the user chose.

    Args:
        path: The file.
        number_column: Column holding the shot number.
        description_column: Column holding the description.

    Returns:
        One entry per row, skipping rows with no shot number.

    Raises:
        ValueError: If a named column is not in the file, listing the columns
            that are — a mistyped header should say what was available.
    """
    # PSEUDOCODE
    # 1. Sniff the delimiter from the suffix and the first line.
    # 2. Read the header; refuse a missing column, naming what was found.
    # 3. Build an entry per row, skipping blank shot numbers.
    raise NotImplementedError


def suggest_columns(path: Path) -> dict:
    """
    Reads the header and proposes which columns to use.

    Returns:
        The header names, plus a suggested number and description column where
        one looks likely. A suggestion the user confirms, never applied
        silently: matching against the wrong column produces confident
        nonsense rather than an error.
    """
    # PSEUDOCODE
    # 1. Read the header row and a few sample rows for the preview.
    # 2. Match names case-insensitively against the likely lists.
    # 3. Return headers, samples, and the suggestions.
    raise NotImplementedError


def read_thumbnails(directory: Path) -> List[ShotListEntry]:
    """
    Finds reference images named by shot number.

    The shot number is the filename without its extension, so `SEQ_0010.jpg`
    is shot `SEQ_0010`. Entries come back with `is_still` set and no
    description — describing them is the vision pass's job, and the pipeline
    does it with the same Observer the videos use.
    """
    # PSEUDOCODE
    # 1. Refuse anything that is not a directory.
    # 2. Take image files, using the stem as the shot number.
    # 3. Return entries with is_still True, sorted by number.
    raise NotImplementedError


def read_text(path: Path, backend: Optional[object] = None) -> List[ShotListEntry]:
    """
    Reads a freeform document into entries.

    Tries structure first — many "documents" are really a list of lines that
    begin with a shot code. Only when that finds nothing does it ask the text
    backend to normalise the document, and the result is always shown for
    confirmation before it is used.

    Raises:
        ValueError: If nothing could be read and no backend was supplied to
            fall back on.
    """
    # PSEUDOCODE
    # 1. Try line-per-shot with a leading code; return if that finds entries.
    # 2. With no backend, raise saying the document could not be read.
    # 3. Otherwise ask the backend for number and description pairs.
    # 4. Return them for confirmation.
    raise NotImplementedError
