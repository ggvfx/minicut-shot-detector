"""
Renaming, and Undoing It.

The only destructive thing either tab does, which is why it has its own module
and its own log.

Three rules, settled before any of it is written:

**Only on approval.** A proposed shot number is a proposal until a person ticks
it. Nothing is renamed because the confidence looked high.

**The name comes from the convention, not from us.** A shot is named by the
production's own scheme — prefix, number, increment, suffix — typed by someone
who knows it. This replaces the filename rather than appending to it, because
the name a tracker expects is the whole name: `PARA_003_4560_blockout_v0001`,
not a mini cut export with that bolted on the end.

The original is not lost by it. It goes into the rename log, and it is a column
in the breakdown export, so the tie back to the mini cut survives in both
places anyone would look.

**Reversible.** Every rename is written to a log beside the files before it
happens, so the whole batch can be put back. A tool that renames forty files
and offers no way back is a tool people are right to be afraid of.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List

from src.core.models import NamingScheme, ShotRecord

# --- THE LOG ---

# Written into the folder being renamed, so it travels with the files rather
# than living in a settings folder on one machine.
RENAME_LOG = ".minicut-renames.json"

# Characters no filesystem will take, plus the separators that would quietly
# turn a name into a path.
ILLEGAL = re.compile(r'[<>:"/\\|?*]')


def number_shots(records: List[ShotRecord], scheme: NamingScheme) -> List[ShotRecord]:
    """
    Names a whole batch from a scheme, in file order.

    Args:
        records: The shots, in the order they should be numbered.
        scheme: Prefix, first number, increment and suffix.

    Returns:
        The same records, each carrying its proposed name in `shot_number`.

    Notes:
        Every shot is numbered, including any already carrying a name: a second
        press after correcting the increment has to renumber the batch, not
        skip most of it. Nothing touches the disk here — this is a proposal,
        and stays one until someone approves it.
    """
    for index, record in enumerate(records):
        record.shot_number = scheme.name_for(index)

    return records


def planned_name(record: ShotRecord) -> str:
    """
    What a file would be called, without touching anything.

    The plan is shown before it is applied — renaming is not the moment to
    discover that two shots would end up with the same name.

    Args:
        record: A shot carrying the name it has been given.

    Returns:
        The new filename with its extension, or the name it already has where
        there is no shot number to apply.
    """
    path = Path(record.file)

    if not record.shot_number:
        return path.name

    return f"{record.shot_number}{path.suffix}"


def check_plan(records: List[ShotRecord]) -> List[str]:
    """
    Finds everything wrong with a rename plan before any of it happens.

    Args:
        records: The shots to be renamed.

    Returns:
        Problems in plain words, empty when the plan is safe. Checked: two
        shots given the same name, a target that already exists, a file that
        has moved since it was analysed, and a shot number carrying characters
        the filesystem will not take.

    Notes:
        All of it is checked before anything is renamed. A half-applied batch
        is the worst outcome — some files renamed, some not, and no way to tell
        which without reading the log.
    """
    planned = [record for record in records if record.approved and record.shot_number]
    problems = []
    seen = {}

    for record in planned:
        source = Path(record.file)
        target = planned_name(record)

        if ILLEGAL.search(record.shot_number):
            problems.append(
                f"{record.shot_number} cannot be a filename — it contains one "
                "of the characters a path is built from"
            )
            # Nothing further can be asked about this one: building a path from
            # a name with a separator in it raises rather than answering, and
            # the problem has already been named.
            continue

        # Compared case-insensitively: Windows would collide silently where a
        # case-sensitive check saw two different names.
        if target.lower() in seen:
            problems.append(
                f"{source.name} and {seen[target.lower()]} would both become {target}"
            )
        else:
            seen[target.lower()] = source.name

        if not source.is_file():
            problems.append(f"{source.name} is no longer where it was")
            continue

        target_path = source.with_name(target)
        if target_path.exists() and target_path != source:
            problems.append(f"{target} already exists in that folder")

    return problems


def apply_renames(records: List[ShotRecord], directory: Path) -> List[ShotRecord]:
    """
    Renames approved files, after writing the log.

    Args:
        records: The shots; approved ones carry the name to apply.
        directory: The folder holding them, and where the log goes.

    Returns:
        The records, with `renamed_to` filled in for each file that moved.

    Raises:
        ValueError: If `check_plan` finds anything. The plan is verified
            immediately before it is applied, not only when it was shown —
            files can change underneath a user who left the tab open.

    Notes:
        The log is written first. A crash between writing and renaming leaves a
        log describing renames that did not happen, which is recoverable; the
        other order leaves renamed files with no record, which is not.
    """
    problems = check_plan(records)
    if problems:
        raise ValueError("; ".join(problems))

    planned = [record for record in records if record.approved and record.shot_number]
    if not planned:
        return records

    entries = [
        {
            "original": Path(record.file).name,
            "renamed_to": planned_name(record),
            "shot_number": record.shot_number,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        for record in planned
    ]

    log = directory / RENAME_LOG
    log.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    for record, entry in zip(planned, entries):
        source = Path(record.file)
        target = source.with_name(entry["renamed_to"])

        source.rename(target)

        # Recorded before the path is overwritten: after this, nothing else
        # knows what the file arrived as.
        record.original_file = record.original_file or source.name
        record.file = str(target)
        record.renamed_to = target.name

    logging.info(f"Renamed {len(planned)} files in {directory}")
    return records


def undo_renames(directory: Path) -> int:
    """
    Puts a batch back to the names it had.

    Args:
        directory: The folder holding the files and the log.

    Returns:
        How many files were restored.

    Notes:
        A file renamed again by hand since is left alone and reported, not
        forced back. The log says what this tool did, and is not a claim to own
        the folder afterwards.
    """
    log = directory / RENAME_LOG
    if not log.is_file():
        return 0

    entries = json.loads(log.read_text(encoding="utf-8"))
    restored = 0

    for entry in entries:
        current = directory / entry["renamed_to"]
        original = directory / entry["original"]

        if not current.is_file():
            logging.warning(f"{entry['renamed_to']} has been renamed again; left alone")
            continue

        if original.exists():
            logging.warning(f"{entry['original']} is back already; left alone")
            continue

        current.rename(original)
        restored += 1

    log.unlink()
    return restored
