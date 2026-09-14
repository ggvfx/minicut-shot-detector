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
from typing import Dict, List, Optional

from pydantic import BaseModel

from src.core import config
from src.core.ffmpeg_tools import MediaToolchain
from src.core.templates import (
    FFMPEG_FALLBACK,
    FFMPEG_INSTALL,
    FREETYPE_FALLBACK,
    FREETYPE_INSTALL,
    PYTHON_FALLBACK,
    PYTHON_INSTALL,
)

# --- STATUS VALUES ---

OK = "ok"
DEGRADED = "degraded"
BLOCKED = "blocked"

# The two tabs. Each is told what it needs and nothing else: the splitter
# needs encoders and PySceneDetect, the identifier needs a model, and neither
# can act on the other's requirements.
SPLITTER = "splitter"
IDENTIFIER = "identifier"

TABS = (SPLITTER, IDENTIFIER)

# Worst wins when rolling individual checks up into one overall status.
STATUS_SEVERITY = {OK: 0, DEGRADED: 1, BLOCKED: 2}

# --- RESULT MODELS ---


class FixStep(BaseModel):
    """
    One way to resolve a failing check.

    A list of these rather than a single command, because one command assumes
    a package manager the user may not have. Every dependency here ends with an
    option that needs nothing installed first.
    """

    label: str                        # "With Homebrew", "Or download a build"
    command: Optional[str] = None     # To paste into a terminal
    url: Optional[str] = None         # To open in a browser


class Check(BaseModel):
    """One row in the dependency panel."""

    key: str                      # Stable id, used by the front end
    label: str                    # What the user reads
    status: str                   # ok | degraded | blocked
    detail: str                   # What was found

    # How to resolve it. Empty on a passing check.
    fixes: List[FixStep] = []

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


def python_fixes() -> List[FixStep]:
    """Ways to install a supported Python on this machine."""
    return _steps(PYTHON_INSTALL, PYTHON_FALLBACK)


def ffmpeg_fixes() -> List[FixStep]:
    """Ways to install ffmpeg on this machine."""
    return _steps(FFMPEG_INSTALL, FFMPEG_FALLBACK)


def freetype_fixes() -> List[FixStep]:
    """Ways to get an ffmpeg that can burn in frame numbers. Always optional."""
    return _steps(FREETYPE_INSTALL, FREETYPE_FALLBACK)


def _steps(options: dict, fallback: list) -> List[FixStep]:
    """
    This platform's options, as panel rows.

    Only this platform's: the app knows which it is on, and showing a Windows
    user the Homebrew line would be noise.
    """
    return [
        FixStep(label=label, command=command, url=url)
        for label, command, url in options.get(platform.system(), fallback)
    ]


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

        # Keyed by tab and output directory together: the tabs produce
        # different lists, and one must never be served the other's.
        self._reports: Dict[str, EnvironmentReport] = {}

    # --- PUBLIC API ---

    def report(
        self,
        tab: str = SPLITTER,
        output_dir: Optional[Path] = None,
        refresh: bool = False,
        extra: Optional[List[Check]] = None,
    ) -> EnvironmentReport:
        """
        The dependency report for one tab, cached between calls.

        Args:
            tab: Which tab is asking. They need different things, so they are
                told different things — see `run_all`.
            output_dir: The user's chosen output directory, so free space is
                measured against the volume actually being used. None until
                they pick one, which is the normal state on launch.
            refresh: Re-run the checks instead of returning the cached report.
            extra: Rows produced elsewhere, appended after this module's own.

        Notes:
            Cached per tab as well as per directory, since the two tabs produce
            different lists and one must not be served the other's.

            Extra rows are not cached against, because they are cheap to
            produce and can change without anything here noticing — a key
            appearing in the environment, a local runtime being started. They
            are re-appended to the cached report each time it is asked for.
        """
        key = f"{tab}:{output_dir}"

        if refresh or key not in self._reports:
            if refresh:
                # The user may have installed something since the last run
                self.toolchain.discover()
                self._reports.clear()
            self._reports[key] = self.run_all(tab, output_dir)

        report = self._reports[key]

        if not extra:
            return report

        checks = [*report.checks, *extra]
        return EnvironmentReport(
            overall=gating_status(checks),
            platform=report.platform,
            checks=checks,
        )

    def run_all(
        self,
        tab: str = SPLITTER,
        output_dir: Optional[Path] = None,
        extra: Optional[List[Check]] = None,
    ) -> EnvironmentReport:
        """
        Runs the checks one tab needs and rolls them up. Ignores the cache.

        Args:
            tab: SPLITTER or IDENTIFIER. **They are told different things on
                purpose.** The splitter needs encoders and PySceneDetect and no
                model at all; the identifier needs a model and neither of those.
                Showing each tab the other's requirements would put rows in
                front of people who cannot act on them, which is the rule the
                panel already follows.
            output_dir: The volume free space is measured against.
            extra: Rows produced by modules this one may not import. The model
                backends are the case: they live in `src/backends/`, and core
                importing a domain package would point the dependency arrow the
                wrong way. The caller assembles them and passes them in.

        Raises:
            ValueError: If the tab is not one this app has.
        """
        if tab not in TABS:
            raise ValueError(f"Unknown tab {tab!r}; expected one of {TABS}")

        # Both tabs read media, so both need the toolchain and somewhere to
        # write. What differs is what they do with it.
        checks = [self.check_python(), self.check_ffmpeg(), self.check_ffprobe()]

        if tab == SPLITTER:
            checks.append(self.check_encoders())
            checks.append(self.check_filters())
            checks.append(self.check_scenedetect())

        checks.append(self.check_disk(output_dir))
        checks.extend(extra or [])

        overall = gating_status(checks)
        logging.info(f"Environment check ({tab}): {overall}")

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
                fixes=[FixStep(label="Install Python 3.11 or newer, then recreate the virtual environment",
                               url="https://www.python.org/downloads/")],
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
                fixes=ffmpeg_fixes(),
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
                fixes=ffmpeg_fixes(),
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
                fixes=ffmpeg_fixes(),
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
                fixes=ffmpeg_fixes(),
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
                fixes=ffmpeg_fixes(),
            )

        return Check(key="encoders", label="Mezzanine encoders", status=OK, detail=", ".join(present))

    def check_filters(self) -> Check:
        """
        The drawtext filter, which burns frame numbers into the review proxy.

        Never blocking. The numbers are a cross-check on the player, not the
        product — without them the proxy still builds, still seeks exactly, and
        the splitter still cuts. Reporting this as a failure would stop someone
        working over a missing convenience.

        Notes:
            It is checked at all because of how it fails otherwise. Homebrew's
            ffmpeg bottle is built without libfreetype and so has no drawtext;
            asking for a filter that does not exist makes ffmpeg reject the
            whole output with "Filter not found", which surfaced as a proxy
            that would not build and no indication why. The proxy now leaves
            the counter out when it is missing, and this row is what says so
            before the job rather than after it.
        """
        if self.toolchain.ffmpeg is None:
            return Check(
                key="filters",
                label="Frame numbers on the proxy",
                status=DEGRADED,
                detail="Cannot check without ffmpeg",
                fixes=ffmpeg_fixes(),
            )

        if self.toolchain.has_filter(config.DRAWTEXT_FILTER):
            return Check(
                key="filters",
                label="Frame numbers on the proxy",
                status=OK,
                detail="drawtext is available",
            )

        return Check(
            key="filters",
            label="Frame numbers on the proxy",
            status=DEGRADED,
            detail=(
                "This ffmpeg has no drawtext filter, so the review proxy will "
                "have no burned-in frame numbers. Everything else works."
            ),
            fixes=freetype_fixes(),
        )

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
                fixes=[
                    FixStep(
                        label="Install the pinned dependencies",
                        command="pip install -r requirements.txt",
                    )
                ],
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
                fixes=[FixStep(label="Create it", command=f'mkdir "{output_dir}"')],
            )

        if not os.access(output_dir, os.W_OK):
            return Check(
                key="output_dir",
                label="Output directory",
                status=BLOCKED,
                detail=f"{output_dir} is not writable",
                fixes=[FixStep(label="Choose a directory you own, or correct its permissions")],
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
                fixes=[FixStep(label="Free some space, or pick an output directory on a larger volume")],
            )

        return Check(key="disk", label="Free disk space", status=OK, detail=detail)
