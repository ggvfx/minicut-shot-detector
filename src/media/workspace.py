"""
The Working Folder.

Everything a job needs but nobody asked for lives in `.minicut-work/` inside
the output directory: the mezzanine, the review proxy, and the scratch the
round trip uses. The delivery folder holds the shots and the sidecar, and
nothing else.

This module owns the folder's naming and its lifecycle. The pipeline decides
when a job is finished with it; what the files are called, which source each
belongs to, and what can safely be deleted is decided here.
"""

import logging
from pathlib import Path
from typing import List, Optional

from src.media.proxy import PROXY_SUFFIX

# --- WORKING FILES ---

# The mezzanine, the review proxy and the round trip's scratch all live here,
# inside the output directory. Keeping them out of the delivery folder means an
# abandoned analysis leaves one obviously temporary folder rather than two large
# files sitting among the shots. Removed when a job passes; kept when one fails,
# because that is when the intermediates are worth having.
WORK_DIRECTORY = ".minicut-work"

# Named after the source, so two jobs sharing an output directory cannot collide
MEZZANINE_SUFFIX = "_mezzanine"

# --- RECLAIMING WORKING FILES ---

# A job that is analysed and then abandoned leaves its mezzanine and proxy
# behind — they are only removed when a split passes. That is deliberate: the
# whole point of preparing first is that the encode survives until the person
# has finished reviewing, and it is reused if they come back to the same
# source. The cost is that trying four files and splitting one quietly spends a
# gigabyte or so per source.
#
# So the space is reported and cleared on request, rather than reclaimed
# behind the user's back: these are files they can rebuild, but only by
# waiting through the encode again.


def work_dir_for(output_dir: Path) -> Path:
    """The working folder inside an output directory."""
    return output_dir / WORK_DIRECTORY


def owning_source(work_file: Path) -> str:
    """
    The source stem a working file belongs to.

    Derived by removing the suffix that was added to it, rather than by asking
    whether the name starts with a source stem — "reel_02" would otherwise
    claim "reel_02_extra_mezzanine.mp4", and clearing the work folder would
    spare the wrong file.

    Scratch that belongs to no source (the round trip's concat list) returns
    its own name, which matches nothing and is therefore always reclaimable.
    """
    stem = work_file.stem

    for suffix in (MEZZANINE_SUFFIX, Path(PROXY_SUFFIX).stem):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]

    return stem


def reclaimable_work(output_dir: Path, keep_source: Optional[Path] = None) -> List[Path]:
    """
    Working files that can be deleted without costing anyone their review.

    Args:
        output_dir: The job's output directory, which holds the work folder.
        keep_source: The source currently being reviewed, whose mezzanine the
            split still needs. Everything is reclaimable when this is None —
            the normal case before anything has been analysed.

    Returns:
        The files, sorted by path. Empty when there is no work folder.
    """
    work_dir = work_dir_for(output_dir)
    if not work_dir.is_dir():
        return []

    keep = keep_source.stem if keep_source else None

    return sorted(
        path for path in work_dir.iterdir()
        if path.is_file() and owning_source(path) != keep
    )


def clear_work(output_dir: Path, keep_source: Optional[Path] = None) -> int:
    """
    Deletes the reclaimable working files and reports what that freed.

    A file that will not delete is logged and skipped rather than failing the
    whole request: one locked file should not stop the other three gigabytes
    going. The work folder itself is removed once it is empty, so an output
    directory that is finished with looks finished with.

    Returns:
        Bytes actually freed.
    """
    freed = 0

    for path in reclaimable_work(output_dir, keep_source):
        size = path.stat().st_size
        try:
            path.unlink()
        except OSError as error:
            logging.warning(f"Could not remove {path}: {error}")
            continue
        freed += size

    work_dir = work_dir_for(output_dir)
    if work_dir.is_dir() and not any(work_dir.iterdir()):
        work_dir.rmdir()

    logging.info(f"Cleared {freed / (1024 ** 3):.2f} GB of working files from {output_dir}")
    return freed
