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

# One of these encoders must exist to build the all-intra mezzanine.
# Many ffmpeg builds ship without either, which otherwise only surfaces mid-job.
MEZZANINE_ENCODERS = ("prores_ks", "dnxhd")

# ProRes 422 at 1080p25 is roughly 1.2 GB per minute, and a job writes a
# mezzanine plus a full set of splits — so budget for two passes of it.
GB_PER_MINUTE_PRORES_1080P25 = 1.2
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
    mezzanine_encoder: str = "prores_ks"   # Verified against this ffmpeg build before a job starts
    keep_mezzanine: bool = True            # Large, but allows re-cutting without re-transcoding

    # Masking
    # Letterbox/pillarbox crop as "w:h:x:y". None means the user has accepted
    # whatever cropdetect found rather than overriding it.
    crop_override: Optional[str] = None


# Default instance used by the UI until the user changes anything.
DEFAULT_CONFIG = ProjectConfig()
