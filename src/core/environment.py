"""
Dependency and Environment Checks.

Powers the panel the user sees on launch. Reports three states, not two:

- ok        Ready to use
- degraded  Will run, but worse (CPU-only inference, tight disk) — the user is
            told the cost and allowed to continue
- blocked   Genuinely cannot run

Every failure carries a copyable fix command rather than just an error string.
"""

import importlib.metadata
import logging
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from src.core import config
from src.core.ffmpeg_tools import MediaToolchain

# --- STATUS VALUES ---

OK = "ok"
DEGRADED = "degraded"
BLOCKED = "blocked"

# Worst wins when rolling individual checks up into one overall status.
STATUS_SEVERITY = {OK: 0, DEGRADED: 1, BLOCKED: 2}

# --- FIX COMMANDS BY PLATFORM ---

FFMPEG_INSTALL = {
    "Windows": "winget install Gyan.FFmpeg",
    "Darwin": "brew install ffmpeg",
    "Linux": "sudo apt install ffmpeg",
}


# --- RESULT MODELS ---


class Check(BaseModel):
    """One row in the dependency panel."""

    key: str                      # Stable id, used by the front end
    label: str                    # What the user reads
    status: str                   # ok | degraded | blocked
    detail: str                   # What was found
    fix: Optional[str] = None     # Copyable command that resolves it

    # Reported, but not counted in the overall status. For a row about
    # something the user may never use: the panel's headline answers "can I do
    # the job in front of me?", and a model backend the Identifier tab needs
    # must not turn a perfectly working Splitter amber. Without this the row
    # repeats the mistake that took the output directory off the panel —
    # announcing a fault the user has no reason to act on.
    advisory: bool = False


class EnvironmentReport(BaseModel):
    """The whole panel: every check plus the worst status among them."""

    overall: str
    platform: str
    checks: List[Check]


# --- HELPERS ---


def gating_status(checks: List[Check]) -> str:
    """
    The panel's headline: the worst status among the checks that gate the app.

    Advisory rows are left out. They describe something the user may never
    need — a model backend for a tab they have not opened — and letting one
    turn a working app amber is how a panel starts being ignored.

    All-advisory is `OK`: nothing is wrong, there is just nothing to gate on.
    """
    return worst_status([check.status for check in checks if not check.advisory])


def ffmpeg_fix() -> str:
    """The right ffmpeg install command for the machine we are running on."""
    return FFMPEG_INSTALL.get(platform.system(), "Install ffmpeg and put it on PATH")


# --- PLATFORM NAMING ---

# Windows 11 still reports itself as major version 10; only the build number
# tells them apart. Anything from this build onwards is 11.
WINDOWS_11_BUILD = 22000


def windows_release(release: str, build: int) -> str:
    """Corrects the release name Windows reports for itself."""
    return "11" if build >= WINDOWS_11_BUILD else release


def platform_name() -> str:
    """
    The operating system, named the way the user would name it.

    The build number is included because it is what actually identifies a
    Windows version, and because this string is recorded in job sidecars.
    """
    system = platform.system()

    if system == "Windows":
        build = sys.getwindowsversion().build
        return f"Windows {windows_release(platform.release(), build)} (build {build})"

    return f"{system} {platform.release()}"


def worst_status(statuses: List[str]) -> str:
    """
    The most severe status in a list, which becomes the panel's overall state.

    An empty list is ok — nothing was found to complain about.
    """
    return max(statuses, key=lambda status: STATUS_SEVERITY[status], default=OK)


# --- CHECKER ---


class EnvironmentChecker:
    """
    Runs the dependency checks and holds the result.

    The checks shell out to ffmpeg several times, so a report is cached until
    the user presses Re-check or picks a different output directory. The
    toolchain is shared rather than rediscovered per check.
    """

    def __init__(self, toolchain: Optional[MediaToolchain] = None):
        """
        Args:
            toolchain: Shared toolchain. A new one is discovered if not given.
        """
        self.toolchain = toolchain or MediaToolchain()

        self._report: Optional[EnvironmentReport] = None
        self._reported_for: Optional[str] = None

    # --- PUBLIC API ---

    def report(
        self,
        output_dir: Optional[Path] = None,
        refresh: bool = False,
        extra: Optional[List[Check]] = None,
    ) -> EnvironmentReport:
        """
        The dependency report, cached between calls.

        Args:
            output_dir: The user's chosen output directory, so free space is
                measured against the volume actually being used. None until
                they pick one, which is the normal state on launch.
            refresh: Re-run the checks instead of returning the cached report.
            extra: Rows produced elsewhere, appended after this module's own.
                See `run_all`.

        Notes:
            Extra rows are not cached against, because they are cheap to
            produce and can change without anything here noticing — a key
            appearing in the environment, a local runtime being started. They
            are re-appended to the cached report each time it is asked for.
        """
        key = str(output_dir)

        if refresh or self._report is None or self._reported_for != key:
            if refresh:
                # The user may have installed something since the last run
                self.toolchain.discover()
            self._report = self.run_all(output_dir)
            self._reported_for = key

        if not extra:
            return self._report

        checks = [*self._report.checks, *extra]
        return EnvironmentReport(
            overall=gating_status(checks),
            platform=self._report.platform,
            checks=checks,
        )

    def run_all(
        self, output_dir: Optional[Path] = None, extra: Optional[List[Check]] = None
    ) -> EnvironmentReport:
        """
        Runs every check and rolls them up. Ignores the cache.

        Args:
            output_dir: The volume free space is measured against.
            extra: Rows produced by modules this one may not import. The model
                backends are the case: they live in `src/backends/`, and core
                importing a domain package would point the dependency arrow the
                wrong way. The caller assembles them and passes them in.
        """
        checks = [
            self.check_python(),
            self.check_ffmpeg(),
            self.check_ffprobe(),
            self.check_encoders(),
            self.check_scenedetect(),
            self.check_disk(output_dir),
            *(extra or []),
        ]

        overall = gating_status(checks)
        logging.info(f"Environment check: {overall}")

        return EnvironmentReport(
            overall=overall,
            platform=platform_name(),
            checks=checks,
        )

    # --- INDIVIDUAL CHECKS ---

    def check_python(self) -> Check:
        """Python version. Older than the minimum cannot run the app at all."""
        current = ".".join(str(part) for part in sys.version_info[:3])
        required = ".".join(str(part) for part in config.MIN_PYTHON)

        if sys.version_info[:2] < config.MIN_PYTHON:
            return Check(
                key="python",
                label="Python",
                status=BLOCKED,
                detail=f"Python {current}; {required} or newer is required",
                fix="Install Python 3.11+, then recreate the virtual environment",
            )

        return Check(key="python", label="Python", status=OK, detail=current)

    def check_ffmpeg(self) -> Check:
        """ffmpeg on PATH. Needed for the mezzanine and every split."""
        if self.toolchain.ffmpeg is None:
            return Check(
                key="ffmpeg",
                label="ffmpeg",
                status=BLOCKED,
                detail="Not found on PATH",
                fix=ffmpeg_fix(),
            )

        return Check(key="ffmpeg", label="ffmpeg", status=OK, detail=self.toolchain.ffmpeg.version)

    def check_ffprobe(self) -> Check:
        """ffprobe on PATH. Needed to read frame rate, duration and timecode."""
        if self.toolchain.ffprobe is None:
            return Check(
                key="ffprobe",
                label="ffprobe",
                status=BLOCKED,
                detail="Not found on PATH",
                fix=ffmpeg_fix(),
            )

        return Check(key="ffprobe", label="ffprobe", status=OK, detail=self.toolchain.ffprobe.version)

    def check_encoders(self) -> Check:
        """
        Mezzanine encoder availability.

        Shots come out in the codec they went in as, so the build needs the
        encoder for each source codec we accept. Checked up front because a
        missing encoder otherwise only surfaces once a long job is running.

        libx264 is required; libx265 only matters for h265 sources, so its
        absence is a limitation rather than a failure.
        """
        if self.toolchain.ffmpeg is None:
            return Check(
                key="encoders",
                label="Mezzanine encoders",
                status=BLOCKED,
                detail="Cannot check without ffmpeg",
                fix=ffmpeg_fix(),
            )

        wanted = sorted(set(config.MEZZANINE_ENCODERS.values()))
        present = [name for name in wanted if self.toolchain.has_encoder(name)]
        missing = [name for name in wanted if name not in present]

        if config.REQUIRED_ENCODER not in present:
            return Check(
                key="encoders",
                label="Mezzanine encoders",
                status=BLOCKED,
                detail=f"This ffmpeg build has no {config.REQUIRED_ENCODER}",
                fix="Install a full ffmpeg build: " + ffmpeg_fix(),
            )

        if missing:
            unsupported = ", ".join(
                codec for codec, encoder in config.MEZZANINE_ENCODERS.items() if encoder in missing
            )
            return Check(
                key="encoders",
                label="Mezzanine encoders",
                status=DEGRADED,
                detail=(
                    f"{', '.join(present)} — no {', '.join(missing)}, "
                    f"so {unsupported} sources cannot be cut"
                ),
                fix="Install a full ffmpeg build: " + ffmpeg_fix(),
            )

        return Check(key="encoders", label="Mezzanine encoders", status=OK, detail=", ".join(present))

    def check_scenedetect(self) -> Check:
        """
        PySceneDetect, which is what finds the cuts.

        Both detection passes come from this package, so its absence is the one
        thing that would leave the app able to cut but not to propose where.
        """
        try:
            import scenedetect  # noqa: F401
        except ImportError:
            return Check(
                key="scenedetect",
                label="PySceneDetect",
                status=BLOCKED,
                detail="Not installed",
                fix="pip install -r requirements.txt",
            )

        try:
            version = importlib.metadata.version("scenedetect")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown version"

        return Check(key="scenedetect", label="PySceneDetect", status=OK, detail=version)

    def check_output_dir(self, output_dir: Optional[Path]) -> Check:
        """
        The chosen output directory must exist and be writable before a job starts.

        Deliberately not in `run_all()`. It is the one check whose problem the
        user cannot do anything about when they open the app: the directory is
        chosen at the END of the workflow, so on a fresh launch this reported
        "Not chosen yet" and dragged the whole panel to degraded — the panel
        said something was wrong when nothing was.

        Nothing is lost by leaving it out. `POST /api/split` refuses a job with
        no output directory, and the pipeline calls `ensure_directory()`, so a
        path that does not exist yet is created rather than an error.

        Kept, and kept tested, because a read-only volume is still a real way
        for a job to fail. If that ever bites, this belongs at the point of
        splitting rather than in the launch panel.
        """
        if output_dir is None:
            return Check(
                key="output_dir",
                label="Output directory",
                status=DEGRADED,
                detail="Not chosen yet",
            )

        if not output_dir.is_dir():
            return Check(
                key="output_dir",
                label="Output directory",
                status=BLOCKED,
                detail=f"{output_dir} does not exist",
                fix=f'mkdir "{output_dir}"',
            )

        if not os.access(output_dir, os.W_OK):
            return Check(
                key="output_dir",
                label="Output directory",
                status=BLOCKED,
                detail=f"{output_dir} is not writable",
                fix="Choose a directory you own, or correct its permissions",
            )

        return Check(key="output_dir", label="Output directory", status=OK, detail=str(output_dir))

    def check_disk(self, output_dir: Optional[Path]) -> Check:
        """
        Free space on the output volume.

        Warned about before a job rather than discovered when the drive fills
        halfway through a transcode.
        """
        target = output_dir if output_dir and output_dir.is_dir() else config.REPO_ROOT
        free_gb = shutil.disk_usage(target).free / (1024 ** 3)

        # Mezzanine plus splits is roughly two copies of the source
        minutes_of_footage = free_gb / (config.GB_PER_MINUTE_INTRA_1080P24 * 2)
        detail = f"{free_gb:.0f} GB free — about {minutes_of_footage:.0f} min of 1080p24 source"

        if free_gb < config.MIN_FREE_GB:
            return Check(
                key="disk",
                label="Free disk space",
                status=DEGRADED,
                detail=f"{detail}, below the {config.MIN_FREE_GB:.0f} GB comfort threshold",
                fix="Free some space, or pick an output directory on a larger volume",
            )

        return Check(key="disk", label="Free disk space", status=OK, detail=detail)
