"""
Breakdown Export.

The tab's second job: not matching shots to names that already exist, but
describing shots that have none yet, so a new project can be entered into a
database without someone typing it all in.

It is nearly free. The descriptions already exist — this is the same
interpretations the matching step works from, written out instead of compared.
That is what the three-pass split buys: the second function is an output
format, not a second feature.

Two files, written together from one set of columns. CSV is what a tracker
imports; .xlsx is what a person opens, reads and sends on. Neither is a
conversion of the other — they are the same rows written twice, so nobody has
to re-export in the other format at the moment they need it.

Thumbnails come from frames the vision pass already sampled. Nothing is
decoded twice.
"""

import csv
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils.exceptions import IllegalCharacterError
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from src.core.models import ShotRecord

# --- OUTPUT ---

EXPORT_CSV = "shot_breakdown.csv"
EXPORT_XLSX = "shot_breakdown.xlsx"
THUMBNAIL_DIR = "thumbnails"

# Deliberately plain, so the file opens in a spreadsheet as readily as it
# imports into a tracker. The exact columns a facility wants will differ; this
# is the set the design assumed and the first thing to be corrected once it has
# been tried against a real import.
EXPORT_COLUMNS = (
    "shot_number",
    "file",
    "original_file",
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

# Roughly the width each column wants in a spreadsheet. Only a starting point —
# a description is long and a shot size is three letters, and a sheet where
# every column is the same width is one nobody can read.
COLUMN_WIDTHS = {
    "shot_number": 30,
    "file": 34,
    "original_file": 34,
    "shot_size": 11,
    "shot_type": 11,
    "characters": 18,
    "location": 20,
    "camera_move": 14,
    "description": 60,
    "thumbnail": 26,
    "confidence": 11,
    "notes": 40,
}


def export_rows(records: List[ShotRecord]) -> List[dict]:
    """
    The table as plain rows, one per shot.

    Args:
        records: The reviewed shots, in the order they should appear.

    Returns:
        One dict per record, keyed by `EXPORT_COLUMNS`.

    Notes:
        Shots with no number are included, with the column empty. A breakdown
        exists precisely to give unnamed shots their numbers, so dropping them
        would remove the rows the user most needs.

        Both writers work from this, so the CSV and the spreadsheet cannot
        disagree about what a row says.
    """
    rows = []

    for record in records:
        reading = record.interpretation
        path = Path(record.file)

        rows.append({
            "shot_number": record.shot_number or "",
            "file": path.name,
            "original_file": record.original_file or "",
            "shot_size": reading.shot_size if reading else "",
            "shot_type": reading.shot_type if reading else "",
            "characters": ", ".join(reading.characters) if reading else "",
            "location": reading.location if reading else "",
            "camera_move": reading.camera_move if reading else "",
            "description": reading.summary if reading else "",
            "thumbnail": f"{THUMBNAIL_DIR}/{_thumbnail_name(record)}",
            "confidence": f"{record.confidence:.2f}",
            "notes": record.notes,
        })

    return rows


def write_csv(records: List[ShotRecord], output_dir: Path) -> Path:
    """
    Writes the breakdown as CSV.

    Args:
        records: The reviewed shots.
        output_dir: Where the file goes; created if it is not there.

    Returns:
        The path written.

    Notes:
        `newline=""` because the csv module writes its own line endings, and
        letting Python translate them again puts a blank line between every
        row on Windows.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / EXPORT_CSV

    with open(target, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(export_rows(records))

    logging.info(f"Wrote {target}")
    return target


def write_xlsx(records: List[ShotRecord], output_dir: Path) -> Path:
    """
    Writes the same breakdown as a spreadsheet.

    Args:
        records: The reviewed shots.
        output_dir: Where the file goes; created if it is not there.

    Returns:
        The path written.

    Notes:
        Same rows as the CSV, from the same function. What the spreadsheet adds
        is only what a person needs to read it: a bold frozen header, column
        widths that suit their contents, and descriptions that wrap instead of
        running under the next column.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / EXPORT_XLSX

    book = Workbook()
    sheet = book.active
    sheet.title = "Shot breakdown"

    sheet.append(list(EXPORT_COLUMNS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in export_rows(records):
        sheet.append([_spreadsheet_safe(row[column]) for column in EXPORT_COLUMNS])

    # The header stays put while someone scrolls forty shots.
    sheet.freeze_panes = "A2"

    for index, column in enumerate(EXPORT_COLUMNS, start=1):
        letter = get_column_letter(index)
        sheet.column_dimensions[letter].width = COLUMN_WIDTHS.get(column, 18)

        if column in ("description", "notes"):
            for cell in sheet[letter][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    try:
        book.save(target)
    except IllegalCharacterError as error:
        # Translated rather than raised as it comes: openpyxl's exceptions are
        # this module's business, and a route that had to import them to catch
        # them would be reaching through the layer for it. It is also not a
        # ValueError, so the obvious catch upstairs would miss it silently.
        raise ValueError(f"a cell held something a spreadsheet will not take: {error}")

    logging.info(f"Wrote {target}")
    return target


def _spreadsheet_safe(value: str) -> str:
    """
    One cell's text, with anything a spreadsheet refuses taken out.

    Args:
        value: The text for one cell.

    Returns:
        The same text without control characters.

    Notes:
        A spreadsheet will not hold control characters and raises rather than
        dropping them, where CSV takes them without comment — so a reply
        carrying a stray escape wrote one file and failed the other.

        That particular escape is stripped where a command's output is read
        now, but a description cached before that fix still carries it, and
        the next tool to colour its output will not announce itself either.
        Cheaper to make the writer impossible to poison than to trust every
        source upstream of it.
    """
    return ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value


def write_thumbnails(records: List[ShotRecord], output_dir: Path) -> List[Path]:
    """
    Writes one representative frame per shot, named to match its row.

    Args:
        records: The reviewed shots.
        output_dir: The export folder; thumbnails go in a subfolder of it.

    Returns:
        The thumbnails written, in record order.

    Notes:
        Named after the shot number where there is one, and after the file
        otherwise, so the export's thumbnail column always points at something
        that exists.

        The frame is copied from the sample the vision pass already took rather
        than decoded again — that work has been paid for once. A shot whose
        frames have been cleared away is skipped and logged, not fabricated.
    """
    thumbnails = output_dir / THUMBNAIL_DIR
    thumbnails.mkdir(parents=True, exist_ok=True)

    written = []

    for record in records:
        frame = first_frame(record)

        if frame is None:
            logging.warning(f"No sampled frame for {Path(record.file).name}")
            continue

        target = thumbnails / _thumbnail_name(record)
        shutil.copy2(frame, target)
        written.append(target)

    logging.info(f"Wrote {len(written)} thumbnails to {thumbnails}")
    return written


def _thumbnail_name(record: ShotRecord) -> str:
    """What a shot's thumbnail is called — its number, or its filename."""
    stem = record.shot_number or Path(record.file).stem
    return f"{stem}.jpg"


def first_frame(record: ShotRecord) -> Optional[Path]:
    """
    The first frame sampled for a shot, if it is still there.

    Notes:
        Looked up by the name the file had when it was sampled. A renamed shot
        keeps its frames under the old stem, so searching by the current name
        alone would find nothing for exactly the shots that have been through
        the rename step.
    """
    from src.identifier.pipeline import FRAMES_DIRECTORY

    path = Path(record.file)
    frames_dir = path.parent / FRAMES_DIRECTORY

    if not frames_dir.is_dir():
        return None

    stems = [path.stem]
    if record.original_file:
        stems.append(Path(record.original_file).stem)

    for stem in stems:
        frames = sorted(frames_dir.glob(f"{stem}_f*.jpg"))
        if frames:
            return frames[0]

    return None
