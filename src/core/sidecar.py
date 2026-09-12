"""
JSON Sidecar Writing.

One sidecar per job, written next to the split shots: the record of how a set
of shots came to exist.

It is what makes a wrong boundary diagnosable. Without it, a shot that starts a
frame late tells you nothing about what the detectors scored, whether they
agreed, or which ffmpeg build cut it.

Functions rather than a class — writing a single file shares no state between
calls. Reading sidecars back is the identifier tab's job and is not built here.
"""

from pathlib import Path
from typing import Dict

from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import JobResult

# --- NAMING ---

SIDECAR_SUFFIX = "_shots.json"


def sidecar_path_for(source_path: Path, output_dir: Path) -> Path:
    """Returns the sidecar path for a source, e.g. 'reel_02_shots.json'."""
    return output_dir / f"{source_path.stem}{SIDECAR_SUFFIX}"


# --- ENVIRONMENT CAPTURE ---


def capture_environment(toolchain: MediaToolchain) -> Dict[str, str]:
    """
    Records the resolved toolchain for reproducibility.

    Args:
        toolchain: The toolchain the job actually ran with, so the versions
            recorded are the ones that produced these boundaries.

    Returns:
        ffmpeg and ffprobe versions, onnxruntime and scenedetect versions, the
        model checksum, the app version and the platform.
    """
    # PSEUDOCODE
    # 1. Start from toolchain.versions().
    # 2. Add the installed onnxruntime and scenedetect versions.
    # 3. Add the model checksum from config, or the file's own hash.
    # 4. Add the app version and platform string.
    raise NotImplementedError


# --- WRITING ---


def write_sidecar(result: JobResult, output_path: Path) -> Path:
    """
    Serialises a completed job to JSON.

    Args:
        result: The finished job, including its validation outcome.
        output_path: Destination, from sidecar_path_for().

    Returns:
        Path to the written file.

    Notes:
        Written whether validation passed or failed. A failed job's sidecar is
        the most useful thing to look at when working out why.
    """
    # PSEUDOCODE
    # 1. result.model_dump() for a plain dictionary (Pydantic v2).
    # 2. json.dump with indent=2 and UTF-8 encoding.
    raise NotImplementedError
