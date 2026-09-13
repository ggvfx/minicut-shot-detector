"""
Identifier Pipeline.

Orders the three passes and owns the cache. Holds no observation, interpretation
or matching logic of its own — it decides what runs, in what order, and what
happens when one shot fails.

The entry points follow what is expensive:

    observe_all()     the vision pass, once per shot, cached to disk
    interpret_all()   text only, re-run whenever knowledge changes
    match_all()       text only, re-run whenever the shot list changes

Split that way because of what a real session looks like: describe forty shots
once, then correct the terminology file, add a character, fix a shot list
column — and get all forty re-matched in seconds without a vision model
touching a single frame again. The splitter learned the same lesson with the
mezzanine, for the same reason.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from src.backends.adapter import ModelBackend
from src.core.ffmpeg_tools import MediaToolchain
from src.identifier.knowledge import ProjectKnowledge
from src.identifier.models import ShotRecord, ShotListEntry

# --- THE CACHE ---

# Written beside the shots, so it survives closing the app and travels with the
# folder. The vision pass is the expensive step and must never be repeated
# because someone shut a browser tab.
CACHE_FILE = ".minicut-observations.json"

# Video files considered. Anything else in the folder is ignored rather than
# refused — a shot folder usually has a sidecar or a spreadsheet in it too.
VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".m4v")


class IdentifierPipeline:
    """
    Runs one identification job over a folder of single-shot files.

    Takes any folder. A splitter sidecar beside the files may be read for frame
    ranges and timecodes, but is never required — most batches arrive from
    somewhere else, and needing one would tie the two tabs together.
    """

    def __init__(
        self,
        directory: Path,
        vision_backend: ModelBackend,
        text_backend: ModelBackend,
        knowledge: Optional[ProjectKnowledge] = None,
        toolchain: Optional[MediaToolchain] = None,
    ):
        """
        Args:
            directory: The folder of single-shot video files.
            vision_backend: Used by the observation pass, and only by it.
            text_backend: Used by interpretation and matching. Often a
                different thing entirely — a studio may run every text pass
                through a CLI it already licenses and point image work
                elsewhere.
            knowledge: The project's markdown files. Without them the tab still
                describes every shot, in plain words, and names nobody.
            toolchain: Shared ffmpeg toolchain, for sampling frames.
        """
        self.directory = directory
        self.vision_backend = vision_backend
        self.text_backend = text_backend
        self.knowledge = knowledge
        self.toolchain = toolchain or MediaToolchain()

    # --- PASSES ---

    def shots(self) -> List[ShotRecord]:
        """
        The video files in the folder, with anything already cached.

        Returns:
            One record per file, in name order, observations filled in from the
            cache where they match.
        """
        # PSEUDOCODE
        # 1. List video files, sorted by name.
        # 2. Load the cache if present.
        # 3. Attach a cached observation where the file is unchanged.
        raise NotImplementedError

    def observe_all(self, records: List[ShotRecord], force: bool = False) -> List[ShotRecord]:
        """
        The vision pass. The slow one, and the only one that needs images.

        Args:
            records: Shots to describe.
            force: Re-observe shots that already have a cached description.

        Notes:
            Cached shots are skipped unless forced. The cache is written after
            each shot rather than at the end: a batch of forty that fails on
            shot thirty-nine must not throw away thirty-eight descriptions.

            A shot that fails is recorded as failed and the batch continues.
            One unreadable file should not stop the other thirty-nine, and a
            failure that reads as an empty description would look like an
            unidentifiable shot instead of a broken backend.
        """
        # PSEUDOCODE
        # 1. For each record without an observation, or all if forced:
        # 2.   Sample frames into the working folder.
        # 3.   Observe them, recording the backend and model used.
        # 4.   Write the cache.
        # 5.   On failure, note it on the record and carry on.
        raise NotImplementedError

    def interpret_all(self, records: List[ShotRecord]) -> List[ShotRecord]:
        """
        The first text pass. Cheap enough to re-run whenever knowledge changes.

        Notes:
            Runs from cached observations, so correcting a terminology file or
            adding a character costs no vision calls at all.
        """
        # PSEUDOCODE
        # 1. Skip records with no observation.
        # 2. Interpret each against the project knowledge.
        # 3. Return the updated records.
        raise NotImplementedError

    def match_all(self, records: List[ShotRecord], entries: List[ShotListEntry]) -> List[ShotRecord]:
        """
        The second text pass. Re-run whenever the shot list changes.

        Notes:
            Leaves `shot_number` unset wherever the comparison could not
            separate the candidates. An unnamed shot is a correct answer.
        """
        # PSEUDOCODE
        # 1. Skip records with no interpretation.
        # 2. Rank the entries for each, and decide.
        # 3. Record number, confidence, note and the full ranking.
        raise NotImplementedError
