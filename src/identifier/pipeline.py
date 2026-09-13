"""
Identifier Pipeline Orchestrator.

Coordinates the stages of an identifier run from a folder of shots to a
reviewed table.

Contains no observation, interpretation or matching logic of its own. It decides
what runs, in what order, what each stage is given, and what happens when one
fails — the same job `SplitterPipeline` does for the other tab, and kept thin
for the same reason.

Two entry points, because a person reviews the matches in between:

    prepare()          Describe every shot, and propose a number for each
    rename() / export()  Act on what the person approved

The expensive work happens in `prepare()`, and the vision pass inside it is
cached beside the shots. Running it again after correcting a terminology file
or adding a character re-interprets and re-matches from that cache without a
single vision call — the same trick as the splitter's `run()` reusing a
mezzanine that already matches its source.

Unlike the splitter this is judgement work and cannot be deterministic, which
is why nothing is written until a person has approved it.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from src.backends.adapter import ModelBackend
from src.core.config import IdentifierConfig
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import ProjectKnowledge, ShotListEntry, ShotRecord

# --- WORKING FILES ---

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

    Holds the config and the shared toolchain, and builds each stage engine as
    it goes so nothing is constructed until it is needed.

    Takes any folder. A splitter sidecar beside the files may be read for frame
    ranges and timecodes, but is never required — most batches arrive from
    somewhere else, and needing one would tie the two tabs together.
    """

    def __init__(self, config: IdentifierConfig, toolchain: Optional[MediaToolchain] = None):
        """
        Args:
            config: Settings for this run. Built by the UI, never here.
            toolchain: Shared ffmpeg toolchain. Discovered if not given.
        """
        self.config = config
        self.toolchain = toolchain or MediaToolchain()

    # --- PIPELINE ---

    def prepare(self, entries: Optional[List[ShotListEntry]] = None) -> List[ShotRecord]:
        """
        Describes every shot in the folder and proposes a number for each.

        Args:
            entries: The shot list to match against. Without one the shots are
                still described — that is the breakdown case, where a project
                has no shot list yet and this is how it gets one.

        Returns:
            One record per video file, in name order: what was seen, what it
            was read as, and what it matched.

        Raises:
            ValueError: If the config has no shots directory.
            RuntimeError: If no usable backend is configured, or the folder
                holds no video files.

        Notes:
            Safe to run again. The vision pass is cached per file, so a second
            run after editing the knowledge files re-interprets and re-matches
            without touching a vision model.
        """
        shots_dir = self._resolve_paths()

        records = self._shots(shots_dir)
        records = self._observe(records, shots_dir)
        records = self._interpret(records)

        if entries:
            records = self._match(records, entries)

        return records

    def rename(self, records: List[ShotRecord]) -> List[ShotRecord]:
        """
        Renames the approved files to carry their shot numbers.

        The first of the two things a person can do with a reviewed table, and
        the only destructive action in either tab.

        Args:
            records: Reviewed records. Only those marked approved and holding a
                shot number are touched.

        Returns:
            The records, with `renamed_to` filled in for each file that moved.

        Raises:
            ValueError: If the plan would collide, overwrite, or name a file
                something the filesystem will not take. Checked in full before
                anything is renamed — a half-applied batch is the worst
                outcome, and the one with no obvious way back.
        """
        # PSEUDOCODE
        # 1. Resolve the shots directory.
        # 2. Hand the approved records to rename.apply_renames, which writes
        #    its log before it moves anything.
        # 3. Return the updated records.
        raise NotImplementedError

    def export(self, records: List[ShotRecord], output_dir: Path) -> Path:
        """
        Writes the breakdown a database is seeded from.

        The second of the two things a person can do with a reviewed table, and
        nearly free: the same interpretations, written out instead of compared.

        Args:
            records: Reviewed records. Shots with no number are written too,
                with the column empty — a breakdown exists to give unnamed
                shots their numbers, so dropping them removes the rows that
                are most the point.
            output_dir: Where the CSV and thumbnails go.

        Returns:
            The path of the written CSV.
        """
        # PSEUDOCODE
        # 1. Write the thumbnails, reusing the frames already sampled.
        # 2. Write the CSV beside them.
        # 3. Return the CSV path.
        raise NotImplementedError

    # --- STAGES ---

    def _resolve_paths(self) -> Path:
        """
        Reads the path every job needs out of the config.

        Raises:
            ValueError: If it is missing. Failing here names the missing
                setting, rather than failing later on a path built from None.
        """
        if not self.config.shots_dir:
            raise ValueError("No folder of shots was chosen")

        return Path(self.config.shots_dir)

    def _shots(self, shots_dir: Path) -> List[ShotRecord]:
        """
        Stage 1. Lists the video files, and reloads anything already described.

        Raises:
            RuntimeError: If the folder holds no video files. Saying so names
                the folder, rather than returning an empty table that looks
                like forty shots nothing could be said about.
        """
        # PSEUDOCODE
        # 1. List video files by suffix, sorted by name.
        # 2. Raise if there are none.
        # 3. Load the cache if present, attaching an observation to each file
        #    whose size and modified time still match what was cached.
        raise NotImplementedError

    def _observe(self, records: List[ShotRecord], shots_dir: Path) -> List[ShotRecord]:
        """
        Stage 2. The vision pass — the slow one, and the only one with images.

        Notes:
            Cached shots are skipped unless the config asks for them again. The
            cache is written after each shot rather than at the end: a batch of
            forty that fails on shot thirty-nine must not throw away
            thirty-eight descriptions.

            A shot that fails is recorded as failed and the batch continues.
            One unreadable file should not stop the other thirty-nine.
        """
        # PSEUDOCODE
        # 1. Build the vision backend from the config.
        # 2. For each record without an observation, or all if force_observe:
        # 3.   Sample frames into the working folder.
        # 4.   Observe them, recording the backend and model used.
        # 5.   Write the cache.
        # 6.   On failure, note it on the record and carry on.
        raise NotImplementedError

    def _interpret(self, records: List[ShotRecord]) -> List[ShotRecord]:
        """
        Stage 3. Reads the observations in the project's own vocabulary.

        Notes:
            Text only, so this is cheap enough to re-run whenever the knowledge
            files change — which is the point of separating it from Stage 2.
        """
        # PSEUDOCODE
        # 1. Build the text backend and load the project knowledge.
        # 2. Skip records with no observation.
        # 3. Interpret each, keeping the observed evidence beside the reading.
        raise NotImplementedError

    def _match(self, records: List[ShotRecord], entries: List[ShotListEntry]) -> List[ShotRecord]:
        """
        Stage 4. Proposes a shot number, or honestly proposes nothing.

        Notes:
            Leaves `shot_number` unset wherever the comparison could not
            separate the candidates. An unnamed shot is a correct answer: a
            wrongly named file is worse and far harder to notice later.
        """
        # PSEUDOCODE
        # 1. Skip records with no interpretation.
        # 2. Rank the entries for each, and decide.
        # 3. Record number, confidence, note and the full ranking.
        raise NotImplementedError

    # --- BACKENDS AND KNOWLEDGE ---

    def _backend(self, which: str) -> ModelBackend:
        """
        Builds the backend for one pass.

        Args:
            which: "vision" or "text". They are configured separately because
                they are routinely different in practice — a studio may run
                every text pass through a CLI it already licenses and have to
                send image work somewhere else.

        Raises:
            RuntimeError: If the configured backend cannot be used. Naming
                which pass it was for is the difference between a puzzle and a
                setting to correct.
        """
        # PSEUDOCODE
        # 1. Take the vision or text BackendConfig from the config.
        # 2. Build it with create_backend.
        # 3. Raise, naming the pass, if it reports itself unavailable.
        raise NotImplementedError

    def _knowledge(self) -> ProjectKnowledge:
        """
        Loads the project's markdown, or an empty set of it.

        Notes:
            Missing knowledge is not a failure. Without it every shot is still
            described, in plain words, and nobody is named — which is exactly
            the breakdown case for a show that has no character sheet yet.
        """
        # PSEUDOCODE
        # 1. Return empty knowledge when no directory is configured.
        # 2. Otherwise load whichever files are present, logging what was found.
        raise NotImplementedError

    @staticmethod
    def _cache_path(shots_dir: Path) -> Path:
        """Where the observations for a folder are remembered."""
        return shots_dir / CACHE_FILE
