"""
Shared Test Fixtures.

Generates short test clips with ffmpeg rather than committing media to the
repository. Every clip has a known frame rate, frame count and geometry, so a
test can assert exact numbers instead of "about right".

Tests needing these are skipped when ffmpeg is not installed, so the suite
still runs on a machine without it.
"""

import shutil
import subprocess

import pytest

from src.core.ffmpeg_tools import MediaToolchain

# --- CLIP DEFINITIONS ---

# Small frames keep generation fast; the numbers are what matter, not the picture.
CLIP_WIDTH = 320
CLIP_HEIGHT = 240

# Each entry is (name, extra input args, filter chain, extra output args).
# Frame counts are exact: 2 seconds at the given rate.
CLIP_SPECS = {
    # 25 fps, constant, with a start timecode — the simple case
    "pal": {
        "rate": "25",
        "duration": "2",
        "filters": None,
        "extra_output": ["-timecode", "10:00:00:00"],
        "expected_frames": 50,
    },
    # 23.976, where the rate is a rational and not a round number
    "film": {
        "rate": "24000/1001",
        "duration": "2",
        "filters": None,
        "extra_output": [],
        "expected_frames": 48,
    },
    # Letterboxed: 320x180 of picture centred in a 320x240 frame, so
    # cropdetect should find 320:180:0:30
    "letterbox": {
        "rate": "25",
        "duration": "2",
        "source_height": 180,
        "filters": "pad=320:240:0:30",
        "extra_output": [],
        "expected_frames": 50,
    },
}


@pytest.fixture(scope="session")
def ffmpeg_available() -> bool:
    """Whether ffmpeg and ffprobe are both on PATH."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture(scope="session")
def toolchain(ffmpeg_available) -> MediaToolchain:
    """A discovered toolchain, skipping the test when ffmpeg is missing."""
    if not ffmpeg_available:
        pytest.skip("ffmpeg is not installed")
    return MediaToolchain()


@pytest.fixture(scope="session")
def clips(ffmpeg_available, tmp_path_factory):
    """
    Generates the test clips once per session.

    Returns:
        dict of clip name -> Path.
    """
    if not ffmpeg_available:
        pytest.skip("ffmpeg is not installed")

    directory = tmp_path_factory.mktemp("clips")
    paths = {}

    for name, spec in CLIP_SPECS.items():
        output = directory / f"{name}.mov"
        height = spec.get("source_height", CLIP_HEIGHT)
        source = f"testsrc=size={CLIP_WIDTH}x{height}:rate={spec['rate']}:duration={spec['duration']}"

        command = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", source]
        if spec["filters"]:
            command += ["-vf", spec["filters"]]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", *spec["extra_output"], str(output)]

        subprocess.run(command, check=True, capture_output=True)
        paths[name] = output

    # Variable frame rate: dropping every other frame for the first part of the
    # clip leaves r_frame_rate and avg_frame_rate disagreeing, which is exactly
    # what the VFR check looks for.
    vfr = directory / "vfr.mov"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc=size={CLIP_WIDTH}x{CLIP_HEIGHT}:rate=25:duration=3",
            "-vf", "select='not(mod(n,2))+gte(n,40)'",
            "-fps_mode", "vfr",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(vfr),
        ],
        check=True,
        capture_output=True,
    )
    paths["vfr"] = vfr

    # Audio only, to prove a source with no video stream is rejected
    audio = directory / "audio_only.mov"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=1",
            "-c:a", "aac",
            str(audio),
        ],
        check=True,
        capture_output=True,
    )
    paths["audio_only"] = audio

    return paths
