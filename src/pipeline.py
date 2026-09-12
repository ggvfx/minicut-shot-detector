"""
Splitter Pipeline Orchestrator.

Coordinates the five stages of a splitter run and reports progress as it goes.

Contains no detection, cutting or validation logic of its own. It decides what
runs, in what order, what each stage is given, and what happens when one fails.
Keeping it thin is what lets any single stage be reasoned about — or replaced —
on its own.

Stage order:
    1. Probe     What is this file, and will the job fit on disk?
    2. Detect    Where are the cuts?
    3. Cut       Mezzanine, then one file per shot
    4. Validate  Do the numbers and the pixels agree?
    5. Report    Write the sidecar
"""

import logging
from pathlib import Path
from typing import Callable, Optional

from src.core.config import ProjectConfig
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import JobResult

# --- PROGRESS REPORTING ---

# The UI subscribes to progress over SSE. The pipeline knows nothing about SSE:
# it calls a plain function, and the server decides what to do with it.
ProgressCallback = Callable[[str, float, str], None]

# Stage names, used in progress updates and the UI.
STAGE_PROBE = "probe"
STAGE_DETECT = "detect"
STAGE_CUT = "cut"
STAGE_VALIDATE = "validate"
STAGE_REPORT = "report"


class SplitterPipeline:
    """
    Runs one splitter job from source file to written sidecar.

    Holds the config, the shared toolchain and the progress callback, and builds
    each stage engine as it goes so nothing is constructed until it is needed.
    """

    def __init__(
        self,
        config: ProjectConfig,
        toolchain: Optional[MediaToolchain] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """
        Args:
            config: Settings for this run. Built by the UI, never here.
            toolchain: Shared ffmpeg toolchain. Discovered if not given.
            progress_callback: Receives (stage, fraction 0-1, message).
        """
        self.config = config
        self.toolchain = toolchain or MediaToolchain()
        self.progress_callback = progress_callback

    # --- PROGRESS ---

    def _report(self, stage: str, fraction: float, message: str) -> None:
        """Sends a progress update if anyone is listening, and logs it either way."""
        logging.info(f"[{stage}] {message}")
        if self.progress_callback is not None:
            self.progress_callback(stage, fraction, message)

    # --- PIPELINE ---

    def run(self) -> JobResult:
        """
        Runs a full splitter job.

        Returns:
            JobResult: the shots, the validation outcome and the environment
            that produced them.

        Raises:
            ValueError: If the config has no source or output directory.
            RuntimeError: If a stage fails in a way that makes the job
                meaningless — an unreadable source, a failed mezzanine, or a
                failed validation.
        """
        # PSEUDOCODE
        # 1. Validate the config, then run each stage in order:
        #    _probe -> _detect -> _cut -> _validate -> _report
        # 2. Let a stage raise; the caller turns that into a UI error.
        raise NotImplementedError

    def _probe(self):
        """Stage 1. Inspects the source and confirms the job can run."""
        # PSEUDOCODE
        # 1. SourceProbe(toolchain).probe() -> SourceInfo.
        # 2. Refuse variable frame rate sources with a clear message — their
        #    frame-to-time mapping is unstable and every boundary would drift.
        # 3. detect_crop() unless config.crop_override is set.
        # 4. estimate_disk_required() and compare against free space.
        raise NotImplementedError

    def _detect(self, source, crop):
        """Stage 2. Finds boundaries and turns them into a shot list."""
        # PSEUDOCODE
        # 1. TransNetDetector(...).detect() for the primary pass.
        # 2. SceneDetectCrossCheck().detect() when config.run_cross_check.
        # 3. reconcile: merge_detections -> apply_minimum_length -> boundaries_to_shots.
        # 4. JobValidator.validate_shot_list() here already — a broken list
        #    should stop the job before an hour of transcoding, not after.
        raise NotImplementedError

    def _cut(self, source, shots, crop):
        """Stage 3. Mezzanine, then one file per shot."""
        # PSEUDOCODE
        # 1. MezzanineBuilder(...).build(), which verifies itself.
        # 2. ShotSplitter(...).extract_all() to write each shot.
        raise NotImplementedError

    def _validate(self, source, shots, mezzanine_path):
        """Stage 4. Arithmetic and round-trip checks on what was written."""
        # PSEUDOCODE
        # 1. JobValidator(toolchain).validate_job().
        # 2. A failure blocks the job and surfaces in the UI — never
        #    warn-and-continue.
        raise NotImplementedError

    def _report(self, source, shots, validation, mezzanine_path) -> JobResult:
        """Stage 5. Captures the environment and writes the sidecar."""
        # PSEUDOCODE
        # 1. sidecar.capture_environment(self.toolchain).
        # 2. Assemble the JobResult and sidecar.write_sidecar(), pass or fail.
        # 3. Remove the mezzanine unless config.keep_mezzanine.
        raise NotImplementedError
