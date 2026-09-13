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
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from src.backends.adapter import BackendError, ModelBackend, create_backend
from src.core.config import PRODUCTION_DIR, IdentifierConfig
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Observation, ProjectKnowledge, ShotListEntry, ShotRecord
from src.core.utils import ensure_directory
from src.identifier.frames import FrameSampler
from src.identifier.interpret import Interpreter
from src.identifier.knowledge import load_knowledge
from src.identifier.observe import Observer

# --- WORKING FILES ---

# Written beside the shots, so it survives closing the app and travels with the
# folder. The vision pass is the expensive step and must never be repeated
# because someone shut a browser tab.
CACHE_FILE = ".minicut-observations.json"

# Video files considered. Anything else in the folder is ignored rather than
# refused — a shot folder usually has a sidecar or a spreadsheet in it too.
VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".m4v")

# Sample frames live here while a batch runs. Inside the shots folder rather
# than beside the shots themselves, for the same reason the splitter puts its
# mezzanine in .minicut-work: an abandoned run leaves one obviously temporary
# folder rather than three hundred loose JPEGs among the deliverables.
FRAMES_DIRECTORY = ".minicut-frames"


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
        if not shots_dir.is_dir():
            raise RuntimeError(f"Not a folder: {shots_dir}")

        files = sorted(
            path for path in shots_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        )

        if not files:
            raise RuntimeError(f"No video files in {shots_dir}")

        cached = self._load_cache(shots_dir)
        records = []

        for path in files:
            record = ShotRecord(file=str(path))
            remembered = cached.get(path.name)

            # Keyed on size as well as name: a shot re-exported under the same
            # name is a different shot, and describing it from the old
            # observation would be silently wrong.
            if remembered and remembered.get("size") == path.stat().st_size:
                record.observation = Observation.model_validate(remembered["observation"])
                record.backend = remembered.get("backend", "")
                record.model = remembered.get("model", "")

            records.append(record)

        logging.info(f"{len(records)} shots in {shots_dir}, {len(cached)} already described")
        return records

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
        outstanding = [
            record for record in records
            if self.config.force_observe or record.observation is None
        ]

        if not outstanding:
            logging.info("Every shot already described; no vision calls needed")
            return records

        observer = Observer(self._backend("vision"))
        sampler = FrameSampler(self.toolchain)
        frames_dir = ensure_directory(shots_dir / FRAMES_DIRECTORY)

        for index, record in enumerate(outstanding, start=1):
            path = Path(record.file)
            logging.info(f"Describing {path.name} ({index} of {len(outstanding)})")

            try:
                frames = sampler.sample(path, frames_dir)
                record.observation = observer.observe(frames)
                record.backend = observer.backend.describe()
                record.model = observer.backend.config.model or ""
            except (BackendError, RuntimeError, ValueError) as error:
                record.notes = f"Could not describe this shot: {error}"
                logging.warning(f"{path.name}: {error}")
                continue

            self._write_cache(shots_dir, records)

        return records

    def _interpret(self, records: List[ShotRecord]) -> List[ShotRecord]:
        """
        Stage 3. Reads the observations in the project's own vocabulary.

        Notes:
            Text only, so this is cheap enough to re-run whenever the knowledge
            files change — which is the point of separating it from Stage 2.
        """
        described = [record for record in records if record.observation]
        if not described:
            return records

        interpreter = Interpreter(self._backend("text"), self._knowledge())

        for record in described:
            try:
                record.interpretation = interpreter.interpret(record.observation)
            except BackendError as error:
                record.notes = f"Could not interpret this shot: {error}"
                logging.warning(f"{Path(record.file).name}: {error}")

        return records

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
        backend = create_backend(getattr(self.config, which))

        if not backend.available():
            raise RuntimeError(
                f"The {which} model is not usable: {backend.describe()}. "
                f"Set it in the Models panel and press Test."
            )

        return backend

    def _knowledge(self) -> ProjectKnowledge:
        """
        Loads the project's markdown, or an empty set of it.

        Notes:
            Missing knowledge is not a failure. Without it every shot is still
            described, in plain words, and nobody is named — which is exactly
            the breakdown case for a show that has no character sheet yet.
        """
        directory = (
            Path(self.config.knowledge_dir) if self.config.knowledge_dir else PRODUCTION_DIR
        )
        knowledge = load_knowledge(directory)

        if not knowledge.has_production:
            logging.info(f"No production notes in {directory}; shots will not be named")

        return knowledge

    # --- THE CACHE ---

    def _load_cache(self, shots_dir: Path) -> dict:
        """
        Observations remembered from a previous run.

        Notes:
            An unreadable cache is ignored rather than fatal. It is an
            optimisation — the worst it can cost is describing the batch again,
            where refusing to start would leave someone unable to work at all.
        """
        path = self._cache_path(shots_dir)
        if not path.is_file():
            return {}

        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            logging.warning(f"Ignoring unreadable cache at {path}: {error}")
            return {}

    def _write_cache(self, shots_dir: Path, records: List[ShotRecord]) -> None:
        """
        Remembers every observation so far.

        Written after each shot rather than at the end of the batch: the vision
        pass is the expensive step, and a failure on shot thirty-nine must not
        cost the thirty-eight that already succeeded.
        """
        remembered = {
            Path(record.file).name: {
                "size": Path(record.file).stat().st_size,
                "observation": record.observation.model_dump(),
                "backend": record.backend,
                "model": record.model,
            }
            for record in records
            if record.observation and Path(record.file).is_file()
        }

        try:
            self._cache_path(shots_dir).write_text(
                json.dumps(remembered, indent=2), encoding="utf-8"
            )
        except OSError as error:
            logging.warning(f"Could not write the observation cache: {error}")

    @staticmethod
    def _cache_path(shots_dir: Path) -> Path:
        """Where the observations for a folder are remembered."""
        return shots_dir / CACHE_FILE
