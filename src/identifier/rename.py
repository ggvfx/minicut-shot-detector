"""
Renaming, and Undoing It.

The only destructive thing either tab does, which is why it has its own module
and its own log.

Three rules, settled before any of it is written:

**Only on approval.** A proposed shot number is a proposal until a person ticks
it. Nothing is renamed because the confidence looked high.

**Appended, never replacing.** The original name is what ties a file back to
the mini cut it came out of, and is often the only record of that. The shot
number goes on the end.

**Reversible.** Every rename is written to a log beside the files before it
happens, so the whole batch can be put back. A tool that renames forty files
and offers no way back is a tool people are right to be afraid of.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List

from src.identifier.models import ShotRecord

# --- THE LOG ---

# Written into the folder being renamed, so it travels with the files rather
# than living in a settings folder on one machine.
RENAME_LOG = ".minicut-renames.json"


def planned_name(record: ShotRecord) -> str:
    """
    What a file would be called, without touching anything.

    The plan is shown before it is applied — renaming is not the moment to
    discover that two shots would end up with the same name.
    """
    # PSEUDOCODE
    # 1. Take the file's stem and suffix.
    # 2. Append the shot number to the stem.
    # 3. Return the new name.
    raise NotImplementedError


def check_plan(records: List[ShotRecord]) -> List[str]:
    """
    Finds everything wrong with a rename plan before any of it happens.

    Returns:
        Problems in plain words, empty when the plan is safe. Checked: two
        shots given the same number, a target name that already exists, a file
        that has moved since it was analysed, and a shot number with
        characters the filesystem will not take.

    Notes:
        All of it is checked before anything is renamed. A half-applied batch
        is the worst outcome — some files renamed, some not, and no way to tell
        which without reading the log.
    """
    # PSEUDOCODE
    # 1. Collect approved records with a shot number.
    # 2. Report duplicate target names.
    # 3. Report targets that already exist on disk.
    # 4. Report sources that have gone missing.
    # 5. Report shot numbers containing path-illegal characters.
    raise NotImplementedError


def apply_renames(records: List[ShotRecord], directory: Path) -> List[ShotRecord]:
    """
    Renames approved files, after writing the log.

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
    # PSEUDOCODE
    # 1. Re-run check_plan; raise on any problem.
    # 2. Write the log: original name, new name, shot number, timestamp.
    # 3. Rename each file, recording what actually moved.
    # 4. Return the updated records.
    raise NotImplementedError


def undo_renames(directory: Path) -> int:
    """
    Puts a batch back to the names it had.

    Returns:
        How many files were restored.

    Notes:
        A file renamed again by hand since is left alone and reported, not
        forced back. The log says what this tool did, and is not a claim to own
        the folder afterwards.
    """
    # PSEUDOCODE
    # 1. Read the log; nothing to do if absent.
    # 2. For each entry, restore the original name where the current name
    #    still matches what was written.
    # 3. Leave anything since renamed by hand, and report it.
    # 4. Remove the log once it is spent.
    raise NotImplementedError
