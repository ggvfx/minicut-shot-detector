"""
Splitter Pipeline Orchestrator.

Coordinates the stages of a splitter run from source file to written sidecar.

Contains no detection, cutting or validation logic of its own. It decides what
runs, in what order, what each stage is given, and what happens when one fails.
Keeping it thin is what lets any single stage be reasoned about — or replaced —
on its own.

Stage order:
    1. Probe     What is this file, and will the job fit on disk?
    2. Shots     Where are the cuts, and does the resulting list add up?
    3. Cut       Mezzanine, then one file per shot
    4. Validate  Do the numbers and the pixels agree?
    5. Report    Write the sidecar, and tidy up

Boundaries are supplied by the caller. Finding them automatically is Phase 4;
until then they are typed by hand, which is deliberate — it means the cutter is
proven on numbers we chose before any detector is allowed to choose them.
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from src.core.config import ProjectConfig
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Boundary, JobResult, ProbeReport, Shot, SourceInfo
from src.core.sidecar import capture_environment, sidecar_path_for, write_sidecar
from src.core.utils import ensure_directory
from src.detection.reconcile import boundaries_to_shots
from src.media.mezzanine import MezzanineBuilder
from src.media.probe import SourceProbe
from src.media.splitter import ShotSplitter
from src.validation.validator import JobValidator

# --- WORKING FILES ---

# The mezzanine sits alongside the shots, named after the source so two jobs in
# one directory cannot collide. Removed when the job passes.
MEZZANINE_SUFFIX = "_mezzanine"

# Scratch space for the round trip, removed afterwards. Hidden so it does not
# look like part of the delivery if a job is interrupted.
WORK_DIRECTORY = ".minicut-work"


class SplitterPipeline:
    """
    Runs one splitter job from source file to written sidecar.

    Holds the config and the shared toolchain, and builds each stage engine as
    it goes so nothing is constructed until it is needed.

    Progress is logged, not streamed. Wiring it to the UI over SSE is its own
    task, and the plumbing waits until there is something to plumb.
    """

    def __init__(self, config: ProjectConfig, toolchain: Optional[MediaToolchain] = None):
        """
        Args:
            config: Settings for this run. Built by the UI, never here.
            toolchain: Shared ffmpeg toolchain. Discovered if not given.
        """
        self.config = config
        self.toolchain = toolchain or MediaToolchain()

    # --- PIPELINE ---

    def run(self, boundaries: List[Boundary]) -> JobResult:
        """
        Runs a full splitter job.

        Args:
            boundaries: The frames on which new shots start. An empty list is
                legitimate and produces one shot covering the whole source.

        Returns:
            JobResult: the shots, the validation outcome and the environment
            that produced them. A failed job still returns a result, with the
            failure described in it, because the sidecar is written either way.

        Raises:
            ValueError: If the config has no source or output directory, or a
                boundary is unusable.
            RuntimeError: If a stage fails in a way that makes the job
                meaningless — an unreadable source, a source that cannot be
                cut accurately, or a mezzanine that does not match its source.
        """
        source_path, output_dir = self._resolve_paths()

        report = self._probe(source_path, output_dir)
        shots = self._shots(boundaries, report.source)
        mezzanine_path, shots = self._cut(report.source, shots, output_dir)
        validation = self._validate(report.source, shots, mezzanine_path, output_dir)

        return self._report(report.source, shots, validation, mezzanine_path, output_dir)

    # --- STAGES ---

    def _resolve_paths(self):
        """
        Reads the two paths every job needs out of the config.

        Raises:
            ValueError: If either is missing. Failing here names the missing
                setting, rather than failing later on a path built from None.
        """
        if not self.config.source_path:
            raise ValueError("No source file was chosen")
        if not self.config.output_dir:
            raise ValueError("No output directory was chosen")

        return Path(self.config.source_path), ensure_directory(Path(self.config.output_dir))

    def _probe(self, source_path: Path, output_dir: Path) -> ProbeReport:
        """
        Stage 1. Inspects the source and confirms the job can run at all.

        Raises:
            RuntimeError: If the source cannot be cut accurately — a variable
                frame rate, in practice. Its own explanation is passed through,
                since it already says what to do about it.
        """
        report = SourceProbe(self.toolchain).inspect(source_path, output_dir)

        if not report.can_split:
            raise RuntimeError(report.refusal_reason)

        for warning in report.warnings:
            logging.warning(warning)

        return report

    def _shots(self, boundaries: List[Boundary], source: SourceInfo) -> List[Shot]:
        """
        Stage 2. Turns boundaries into shots, and checks the list adds up.

        The arithmetic runs here, before any transcoding: a shot list that does
        not tile the source is wrong however long you spend cutting it.

        Raises:
            RuntimeError: If the list does not add up, listing what is wrong.
        """
        shots = boundaries_to_shots(boundaries, source.frame_count)

        integrity = JobValidator(self.toolchain).validate_shot_list(shots, source)
        if not integrity.passed:
            raise RuntimeError("The shot list does not add up: " + "; ".join(integrity.failures))

        logging.info(f"{len(shots)} shots to cut")
        return shots

    def _cut(self, source: SourceInfo, shots: List[Shot], output_dir: Path):
        """
        Stage 3. Builds the mezzanine, then writes one file per shot.

        Returns:
            (mezzanine_path, shots) with each shot's file recorded.
        """
        source_path = Path(source.path)
        mezzanine_path = output_dir / f"{source_path.stem}{MEZZANINE_SUFFIX}{source_path.suffix}"

        MezzanineBuilder(self.toolchain).build(source, mezzanine_path)
        shots = ShotSplitter(self.toolchain, mezzanine_path, source, output_dir).extract_all(shots)

        return mezzanine_path, shots

    def _validate(self, source: SourceInfo, shots: List[Shot], mezzanine_path: Path, output_dir: Path):
        """
        Stage 4. Arithmetic and a pixel check on what was actually written.

        A failure does not raise: it travels in the result so the sidecar can
        record it, and the UI can show which check failed and why.
        """
        return JobValidator(self.toolchain).validate_job(
            shots,
            source,
            mezzanine_path,
            output_dir / WORK_DIRECTORY,
            full_round_trip=self.config.full_round_trip,
        )

    def _report(self, source, shots, validation, mezzanine_path: Path, output_dir: Path) -> JobResult:
        """
        Stage 5. Writes the sidecar and tidies up.

        The mezzanine is removed when the job passed and kept when it failed,
        because a failure is exactly when the intermediate is worth having.
        """
        keep_mezzanine = not validation.passed

        result = JobResult(
            source=source,
            shots=shots,
            validation=validation,
            environment=capture_environment(self.toolchain),
            mezzanine_path=str(mezzanine_path) if keep_mezzanine else None,
        )

        sidecar_path = sidecar_path_for(Path(source.path), output_dir)
        result.sidecar_path = str(write_sidecar(result, sidecar_path))

        if keep_mezzanine:
            logging.warning(
                f"Validation failed, so the mezzanine is kept at {mezzanine_path} "
                f"for working out why"
            )
        else:
            mezzanine_path.unlink(missing_ok=True)

        shutil.rmtree(output_dir / WORK_DIRECTORY, ignore_errors=True)

        logging.info(
            f"Job {'passed' if validation.passed else 'FAILED'}: "
            f"{len(shots)} shots in {output_dir}"
        )
        return result
