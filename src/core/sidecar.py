"""
JSON Sidecar Writing and Loading.

One sidecar per job, written next to the split shots. It is the handover format
to the identifier tab and the record of how a set of shots came to exist.

Functions rather than a class: writing and reading share no state, and the
identifier will call `load_sidecar()` with no toolchain and no config at all.

The environment block matters as much as the shots. When a boundary looks wrong
months later, the resolved ffmpeg build, onnxruntime version and model checksum
are how you work out what produced it.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

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


def load_sidecar(path: Path) -> Optional[JobResult]:
    """
    Reads a sidecar back into a JobResult, re-validating it on the way in.

    Returns:
        JobResult, or None when the file is missing or corrupt. This is how the
        identifier tab will pick up a completed splitter job.
    """
    # PSEUDOCODE
    # 1. Return None if the path does not exist.
    # 2. json.load, then JobResult(**data) so Pydantic re-validates.
    # 3. Log and return None on JSONDecodeError or validation failure.
    raise NotImplementedError
