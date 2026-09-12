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

import importlib.metadata
import json
import logging
from pathlib import Path
from typing import Dict

from src.core import config
from src.core.environment import platform_name
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import JobResult
from src.core.utils import file_sha256

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
    environment = {
        "app": f"{config.APP_NAME} {config.APP_VERSION}",
        "platform": platform_name(),
        **toolchain.versions(),
    }

    for package in ("onnxruntime", "scenedetect"):
        try:
            environment[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            # Recorded as absent rather than omitted: a sidecar that simply
            # lacks the key cannot be told apart from an older format
            environment[package] = "not installed"

    if config.MODEL_PATH.is_file():
        environment["model_sha256"] = file_sha256(config.MODEL_PATH)
    else:
        environment["model_sha256"] = "no model present"

    return environment


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
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result.model_dump(), handle, indent=2, ensure_ascii=False)

    outcome = "passed" if result.validation.passed else "FAILED validation"
    logging.info(f"Wrote sidecar for {len(result.shots)} shots ({outcome}): {output_path}")

    return output_path
