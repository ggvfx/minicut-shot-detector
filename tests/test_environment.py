"""
Tests for the Dependency Checks.

Checks that do not need ffmpeg installed are tested directly. The toolchain is
constructed with discover=False where a missing-tool result is what we want.
"""

from src.core.environment import (
    BLOCKED,
    DEGRADED,
    OK,
    IDENTIFIER,
    SPLITTER,
    EnvironmentChecker,
    platform_name,
    windows_release,
    worst_status,
)
from src.core.ffmpeg_tools import MediaToolchain

# --- PLATFORM NAMING ---


def test_windows_11_is_not_called_windows_10():
    """
    Windows 11 reports its release as "10"; only the build tells them apart.

    Taking platform.release() at face value labels every Windows 11 machine as
    Windows 10, which makes the panel look broken to anyone reading it.
    """
    assert windows_release("10", 26200) == "11"
    assert windows_release("10", 22000) == "11"
    assert windows_release("10", 19045) == "10"


def test_platform_name_is_not_empty():
    assert platform_name().strip()


# --- STATUS ROLL-UP ---


def test_worst_status_picks_the_most_severe():
    """The panel's overall state is the worst individual check."""
    assert worst_status([OK, OK, OK]) == OK
    assert worst_status([OK, DEGRADED, OK]) == DEGRADED
    assert worst_status([OK, DEGRADED, BLOCKED]) == BLOCKED
    assert worst_status([]) == OK


# --- INDIVIDUAL CHECKS ---


def test_python_check_passes_on_a_supported_version():
    """These tests only run on a supported interpreter, so this must pass."""
    check = EnvironmentChecker(MediaToolchain(discover=False)).check_python()

    assert check.status == OK
    assert not check.fixes, "a passing check should not offer a fix"


def test_missing_ffmpeg_is_blocked_and_offers_a_fix():
    """A blocked check must always carry a copyable fix command."""
    checker = EnvironmentChecker(MediaToolchain(discover=False))

    ffmpeg = checker.check_ffmpeg()
    assert ffmpeg.status == BLOCKED
    assert ffmpeg.fixes, "a missing dependency must tell the user how to install it"

    encoders = checker.check_encoders()
    assert encoders.status == BLOCKED
    assert encoders.fixes


def test_output_dir_unchosen_is_degraded_not_blocked(tmp_path):
    """
    Not having picked an output directory yet is not a failure.

    The user has just opened the app; the panel should not be red because of it.
    """
    checker = EnvironmentChecker(MediaToolchain(discover=False))

    assert checker.check_output_dir(None).status == DEGRADED
    assert checker.check_output_dir(tmp_path).status == OK


def test_output_dir_missing_is_blocked(tmp_path):
    """A typed path that does not exist blocks the job, with a mkdir fix."""
    check = EnvironmentChecker(MediaToolchain(discover=False)).check_output_dir(
        tmp_path / "does-not-exist"
    )

    assert check.status == BLOCKED
    assert any("mkdir" in (f.command or "") for f in check.fixes)


def test_disk_check_reports_free_space(tmp_path):
    """Free space is reported in GB against the chosen volume."""
    check = EnvironmentChecker(MediaToolchain(discover=False)).check_disk(tmp_path)

    assert check.status in (OK, DEGRADED), "free space is never a hard block"
    assert "GB free" in check.detail


# --- REPORT ---


def test_report_is_cached_until_refreshed(tmp_path):
    """
    The same report object comes back until a refresh is asked for.

    The checks shell out to ffmpeg several times, so repeating them on every
    panel poll would be several subprocesses per second.
    """
    checker = EnvironmentChecker(MediaToolchain(discover=False))

    first = checker.report(SPLITTER, tmp_path)
    second = checker.report(SPLITTER, tmp_path)
    assert first is second, "an unchanged request should return the cached report"

    third = checker.report(SPLITTER, tmp_path, refresh=True)
    assert third is not first, "refresh=True must re-run the checks"


def test_a_fresh_launch_reports_nothing_about_the_output_directory():
    """
    Opening the app without having chosen an output directory is not a fault.

    The directory is picked at the end of the workflow, so a panel that reports
    on it at launch tells the user something is wrong before they have had the
    chance to do anything — and they cannot clear it until they are finished.
    """
    report = EnvironmentChecker(MediaToolchain(discover=False)).report(SPLITTER, None)

    assert not any(check.key == "output_dir" for check in report.checks)
    assert any(check.key == "disk" for check in report.checks), (
        "free space is still reported, against the default volume until one is chosen"
    )


def test_report_rechecks_when_the_output_directory_changes(tmp_path):
    """Disk and writability are per-volume, so a new directory invalidates the cache."""
    checker = EnvironmentChecker(MediaToolchain(discover=False))
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()

    first = checker.report(SPLITTER, tmp_path)
    second = checker.report(SPLITTER, other_dir)

    assert first is not second


def test_report_contains_every_check(tmp_path):
    """
    Every check appears in the panel, with a valid status.

    The output directory is deliberately absent. It is chosen at the end of the
    workflow, so checking it on launch only ever said "not chosen yet" — a
    fault the user could not clear until they had finished. The check itself is
    still here and still tested, just not in the panel.
    """
    report = EnvironmentChecker(MediaToolchain(discover=False)).report(SPLITTER, tmp_path)

    keys = {check.key for check in report.checks}
    assert keys == {
        "python",
        "ffmpeg",
        "ffprobe",
        "encoders",
        "scenedetect",
        "disk",
    }, "the panel reports what this version needs, not what a later one might"

    for check in report.checks:
        assert check.status in (OK, DEGRADED, BLOCKED)
        assert check.detail, f"{check.key} must say what was found"


def test_each_tab_is_told_what_it_needs_and_nothing_else(tmp_path):
    """
    The two tabs have genuinely different requirements.

    The splitter re-encodes and detects cuts, so it needs the encoders and
    PySceneDetect. The identifier does neither — it samples frames and sends
    them to a model. Showing each the other's requirements would put rows in
    front of people who cannot act on them.
    """
    checker = EnvironmentChecker(MediaToolchain(discover=False))

    splitter = {check.key for check in checker.report(SPLITTER, tmp_path).checks}
    identifier = {check.key for check in checker.report(IDENTIFIER, tmp_path).checks}

    assert {"encoders", "scenedetect"} <= splitter
    assert not {"encoders", "scenedetect"} & identifier

    assert {"python", "ffmpeg", "ffprobe", "disk"} <= splitter & identifier, (
        "both read media, so both report the toolchain"
    )


def test_one_tab_is_never_served_the_other_s_cached_report(tmp_path):
    """The cache is keyed by tab as well as directory, or they would collide."""
    checker = EnvironmentChecker(MediaToolchain(discover=False))

    splitter = checker.report(SPLITTER, tmp_path)
    identifier = checker.report(IDENTIFIER, tmp_path)

    assert splitter is not identifier
    assert splitter is checker.report(SPLITTER, tmp_path), "still cached per tab"


def test_an_unknown_tab_is_refused(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="Unknown tab"):
        EnvironmentChecker(MediaToolchain(discover=False)).run_all("sideways", tmp_path)
