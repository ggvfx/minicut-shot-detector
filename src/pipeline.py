"""
Splitter Pipeline Orchestrator.

Coordinates the stages of a splitter run from source file to written sidecar.

Contains no detection, cutting or validation logic of its own. It decides what
runs, in what order, what each stage is given, and what happens when one fails.
Keeping it thin is what lets any single stage be reasoned about — or replaced —
on its own.

Two entry points, because a person reviews the cuts in between:

    prepare()  Probe, build the mezzanine, build the review proxy
    run()      Turn boundaries into shots, cut, validate, write the sidecar

The expensive work happens in prepare(), so scrubbing through the proxy and
adjusting boundaries costs nothing, and cutting afterwards is stream copies.
run() reuses a mezzanine that is already there and still matches its source,
so the two calls together encode the file once.

`prepare()` proposes boundaries; `run()` takes whatever the person settled on.
Detection is a starting point, never the last word: every boundary is reviewed
before anything is written, which is what lets a detector that occasionally
misses a wipe still be useful.
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from src.core.config import ProjectConfig
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Boundary, JobResult, PreparedJob, ProbeReport, Shot, SourceInfo
from src.core.sidecar import capture_environment, sidecar_path_for, write_sidecar
from src.core.utils import ensure_directory
from src.detection.reconcile import boundaries_to_shots, merge_detections
from src.detection.scene_detect import detect_all
from src.media.mezzanine import MezzanineBuilder
from src.media.probe import SourceProbe
from src.media.proxy import PROXY_SUFFIX, ProxyBuilder
from src.media.splitter import ShotSplitter
from src.validation.integrity import validate_shot_list
from src.validation.validator import JobValidator

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


class SplitterPipeline:
    """
    Runs one splitter job from source file to written sidecar.

    Holds the config and the shared toolchain, and builds each stage engine as
    it goes so nothing is constructed until it is needed.

    Progress is logged, not streamed. Streaming it was measured and dropped:
    the worst realistic source prepares in well under a minute, which does not
    pay for progress callbacks threaded through every stage.
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

    def prepare(self) -> PreparedJob:
        """
        Gets a source ready for its cuts to be reviewed.

        Probes it, builds the mezzanine, and builds the small proxy the browser
        plays while boundaries are chosen. Finding those boundaries
        automatically joins here in Phase 4.

        Doing this before review rather than after is what makes the interaction
        bearable: the slow work happens once, up front, and cutting afterwards
        is stream copies.

        Returns:
            PreparedJob: the probed source and the two files review needs.

        Raises:
            ValueError: If the config has no source or output directory.
            RuntimeError: If the source cannot be cut accurately, or the
                mezzanine does not match it.
        """
        source_path, output_dir = self._resolve_paths()
        report = self._probe(source_path, output_dir)

        mezzanine_path = self._mezzanine(report.source, output_dir)
        proxy_path = ProxyBuilder(self.toolchain).build(
            mezzanine_path,
            ProxyBuilder.proxy_path_for(report.source, self._work_dir(output_dir)),
        )

        return PreparedJob(
            source=report.source,
            mezzanine_path=str(mezzanine_path),
            proxy_path=str(proxy_path),
            boundaries=self._detect(mezzanine_path),
        )

    def _detect(self, mezzanine_path: Path) -> List[Boundary]:
        """
        Finds the cuts, as a starting point for review rather than an answer.

        Runs against the mezzanine rather than the source: it is verified frame
        for frame against it, and being all-intra it decodes without seeking
        back to a keyframe for every read.

        Both detectors run and their findings are merged. Anything only one of
        them found is kept and marked, because measuring them showed each
        finding real cuts the other missed.
        """
        return merge_detections(*detect_all(mezzanine_path))

    def run(self, boundaries: List[Boundary]) -> JobResult:
        """
        Runs a full splitter job, preparing the source first if needed.

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

        mezzanine_path = self._mezzanine(report.source, output_dir)
        shots = ShotSplitter(
            self.toolchain, mezzanine_path, report.source, output_dir
        ).extract_all(shots)

        validation = self._validate(report.source, shots, mezzanine_path, output_dir)

        return self._report(report.source, shots, validation, mezzanine_path, output_dir)

    # --- STAGES ---

    @staticmethod
    def _work_dir(output_dir: Path) -> Path:
        """Where the mezzanine, the proxy and the round trip's scratch live."""
        return work_dir_for(output_dir)

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

        # Plain arithmetic: no toolchain, no files, nothing to decode
        integrity = validate_shot_list(shots, source)
        if not integrity.passed:
            raise RuntimeError("The shot list does not add up: " + "; ".join(integrity.failures))

        logging.info(f"{len(shots)} shots to cut")
        return shots

    def _mezzanine(self, source: SourceInfo, output_dir: Path) -> Path:
        """
        Stage 3. The all-intra intermediate every shot is cut from.

        Reuses one that is already there and still matches the source, so
        reviewing boundaries and then cutting does not encode the same file
        twice. The path is derived from the source name rather than remembered
        between requests, which keeps the server free of session state.
        """
        source_path = Path(source.path)
        work_dir = ensure_directory(self._work_dir(output_dir))
        mezzanine_path = work_dir / f"{source_path.stem}{MEZZANINE_SUFFIX}{source_path.suffix}"

        builder = MezzanineBuilder(self.toolchain)

        if mezzanine_path.is_file() and builder.verify(source, mezzanine_path):
            logging.info(f"Reusing the mezzanine already at {mezzanine_path}")
            return mezzanine_path

        return builder.build(source, mezzanine_path)

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
            self._work_dir(output_dir),
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
                f"Validation failed, so the working files are kept in "
                f"{self._work_dir(output_dir)} for working out why"
            )
        else:
            # Mezzanine, proxy and scratch go together: review is over, and the
            # shots are what was actually asked for
            shutil.rmtree(self._work_dir(output_dir), ignore_errors=True)

        logging.info(
            f"Job {'passed' if validation.passed else 'FAILED'}: "
            f"{len(shots)} shots in {output_dir}"
        )
        return result
