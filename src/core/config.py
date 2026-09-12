"""
Global Configuration Management.

Holds fixed project constants and the per-run settings object.
Designed to be serializable so the UI can save and restore a job setup.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# --- PROJECT PATHS ---

# src/core/config.py -> repo root is two parents up
REPO_ROOT = Path(__file__).resolve().parents[2]

MODELS_DIR = REPO_ROOT / "models"
MODEL_PATH = MODELS_DIR / "transnetv2.onnx"
STATIC_DIR = REPO_ROOT / "src" / "ui" / "static"

# Checksum of the committed ONNX export. Filled in when detection lands;
# until then the environment check reports "present" without verifying.
MODEL_SHA256: Optional[str] = None

# --- FIXED REQUIREMENTS ---

MIN_PYTHON = (3, 11)

# Shots come out in the codec they went in as. The mezzanine is an all-intra
# version of the source, so this maps what ffprobe reports to the encoder that
# writes it. ffprobe calls h265 "hevc".
MEZZANINE_ENCODERS = {
    "h264": "libx264",
    "hevc": "libx265",
}

# Without this one, nothing can be cut at all. libx265 only matters for h265
# sources, so its absence is a limitation rather than a failure.
REQUIRED_ENCODER = "libx264"

# Quality of the all-intra mezzanine. Cutting on an arbitrary frame means one
# re-encode generation — unavoidable, since long-GOP frames are defined
# relative to their neighbours and a file can only start on a keyframe.
# CRF 12 is visually transparent for this material, where the source's own
# compression artefacts dominate anything the re-encode adds.
MEZZANINE_CRF = 12
MEZZANINE_PRESET = "veryfast"

# All-intra h264 at CRF 12 measures 0.21 GB per minute at 1080p24, and a job
# writes a mezzanine plus a full set of splits — so budget for two passes.
# Rounded up, because warning early costs nothing and warning late means the
# drive fills mid-transcode.
GB_PER_MINUTE_INTRA_1080P24 = 0.25

# The rate the figure above is quoted at, used to scale other frame rates.
REFERENCE_RATE = 24
MIN_FREE_GB = 20.0

# Extensions the path picker offers as source media.
VIDEO_SUFFIXES = {".mov", ".mp4", ".mxf", ".mkv", ".avi", ".m4v", ".mpg", ".mpeg", ".webm"}

# --- SERVER ---

# Loopback only. The browse endpoint lists this machine's filesystem, so the
# server must never listen on a public interface.
HOST = "127.0.0.1"
PORT = 8765


class ProjectConfig(BaseModel):
    """
    Settings for a single splitter run.

    A passive container — nothing here performs work. The pipeline reads these
    values and hands them down to the stage modules.
    """

    # Path Persistence
    source_path: Optional[str] = None      # The mini cut to split
    output_dir: str = "outputs"            # Mezzanine, shot files and sidecar land here
    last_directory: str = ""               # Where the path picker reopens

    # Detection Logic
    transnet_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    # Shots shorter than this are merged into a neighbour. This is the
    # flash-frame filter, and flashes are the main source of false positives.
    min_shot_length_frames: int = Field(default=7, ge=1)
    # The second detector exists so that disagreement can flag a boundary for
    # review. Leaving it on is what makes an unattended run safe.
    run_cross_check: bool = True

    # Mezzanine & Cutting
    # The encoder is not a setting: it follows the source codec, because shots
    # come out in the format they went in as.
    keep_mezzanine: bool = True            # Allows re-cutting without re-encoding again

    # Masking is deliberately absent: detected letterboxing is reported, never
    # applied, so there is nothing for the user to override.
