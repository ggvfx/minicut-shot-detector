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
from pathlib import Path
from typing import List, Optional

import pytest

from src.backends.adapter import BackendConfig, ModelBackend, ModelReply
from src.core.ffmpeg_tools import MediaToolchain

# --- A BACKEND THAT DOES NOT THINK ---


class ScriptedBackend(ModelBackend):
    """
    Answers from a script, and keeps what it was asked.

    A real backend cannot be asserted against: the same input can give a
    different answer twice, which is the whole reason each record remembers
    what produced it. What can be asserted is what we sent, how many times, and
    that the frames went with it.

    Shared by the observation, interpretation and pipeline tests — all three
    need the same stand-in, and three copies would drift.
    """

    def __init__(self, reply: str = "", replies: Optional[List[str]] = None):
        """
        Args:
            reply: The answer to every call.
            replies: One answer per call, in order, for a test that needs the
                third shot in a batch to fail. A `BackendError` instance in the
                list is raised instead of returned.
        """
        super().__init__(BackendConfig(model="scripted-1"))
        self.reply = reply
        self.replies = replies
        self.prompts: List[str] = []
        self.images: List[List[Path]] = []

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        self.prompts.append(prompt)
        self.images.append(list(images or []))

        answer = self.replies[len(self.prompts) - 1] if self.replies else self.reply
        if isinstance(answer, Exception):
            raise answer

        return ModelReply(text=answer, backend="scripted", model="scripted-1", seconds=0.0)

    @property
    def calls(self) -> int:
        """How many times it was asked — what a cache test is really checking."""
        return len(self.prompts)

    def available(self) -> bool:
        return True

    def describe(self) -> str:
        return "scripted"

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

    # Video with a soundtrack, to prove audio survives the mezzanine. Most real
    # mini cuts have sound; two of the six reference deliveries do not.
    with_audio = directory / "with_audio.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc=size={CLIP_WIDTH}x{CLIP_HEIGHT}:rate=24:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            str(with_audio),
        ],
        check=True,
        capture_output=True,
    )
    paths["with_audio"] = with_audio

    # h265, because its keyframe interval is set differently from h264 and its
    # stream-copy behaviour is proven rather than assumed
    h265 = directory / "h265.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc=size={CLIP_WIDTH}x{CLIP_HEIGHT}:rate=24:duration=2",
            "-c:v", "libx265", "-preset", "ultrafast", "-tag:v", "hvc1",
            "-pix_fmt", "yuv420p",
            str(h265),
        ],
        check=True,
        capture_output=True,
    )
    paths["h265"] = h265

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
