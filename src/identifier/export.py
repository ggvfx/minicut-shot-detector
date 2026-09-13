"""
Breakdown Export.

The tab's second job: not matching shots to names that already exist, but
describing shots that have none yet, so a new project can be entered into a
database without someone typing it all in.

It is nearly free. The descriptions already exist — this is the same
interpretations the matching step works from, written out instead of compared.
That is what the three-pass split buys: the second function is an output
format, not a second feature.

A CSV plus a folder of thumbnails, in the shape shot-tracking software expects.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List

from src.core.models import ShotRecord

# --- OUTPUT ---

EXPORT_CSV = "shot_breakdown.csv"
THUMBNAIL_DIR = "thumbnails"

# Deliberately plain, so the file opens in a spreadsheet as readily as it
# imports into a tracker. The exact columns a facility wants will differ; this
# is the set the design assumed and the first thing to be corrected once it has
# been tried against a real import.
EXPORT_COLUMNS = (
    "shot_number",
    "file",
    "shot_size",
    "shot_type",
    "characters",
    "location",
    "camera_move",
    "description",
    "thumbnail",
    "confidence",
    "notes",
)


def write_csv(records: List[ShotRecord], output_dir: Path) -> Path:
    """
    Writes the breakdown.

    Notes:
        Shots with no number are written too, with the column empty. A
        breakdown exists precisely to give unnamed shots their numbers, so
        dropping them would remove the rows the user most needs.
    """
    # PSEUDOCODE
    # 1. Create the output directory.
    # 2. Write the header, then one row per record in file order.
    # 3. Flatten characters to a separated list.
    # 4. Return the path.
    raise NotImplementedError


def write_thumbnails(records: List[ShotRecord], output_dir: Path) -> List[Path]:
    """
    Writes one representative frame per shot, named to match its row.

    Notes:
        Named after the shot number where there is one, and after the file
        otherwise, so the CSV's thumbnail column always points at something
        that exists.
    """
    # PSEUDOCODE
    # 1. Create the thumbnail directory.
    # 2. Reuse the frame already sampled for each shot rather than decoding
    #    again — the vision pass has been there once already.
    # 3. Return the written paths.
    raise NotImplementedError


def suggest_numbers(
    records: List[ShotRecord], prefix: str, start: int = 10, step: int = 10
) -> List[ShotRecord]:
    """
    Proposes sequential shot numbers for a breakdown.

    Numbering in tens is the convention that leaves room to insert a shot later
    without renumbering everything after it.

    **Open question, not a settled feature.** Whether this belongs here at all
    is undecided: every facility numbers differently, and a wrong convention
    applied to forty shots is worse than no convention. Do not build it until
    it has been asked for against a real project's naming rules.
    """
    # PSEUDOCODE
    # 1. Walk records in file order.
    # 2. Assign prefix + number, incrementing by step, skipping any that
    #    already have a number.
    # 3. Return the records, proposed but not approved.
    raise NotImplementedError
