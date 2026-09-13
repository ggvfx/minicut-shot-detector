"""
Shared Configuration.

**Used by both tabs.** Fixed project constants, and the per-run settings object
for each tab — `ProjectConfig` for the splitter, `IdentifierConfig` for the
identifier. Both are serialisable, so the UI can save and restore a job setup.

One file, so there is one place to look for what a setting is and what it
defaults to. No module invents its own default for anything a user can change;
a module may hold a tuning constant it alone uses, next to the comment
explaining the number.

Split this per-tab only when it grows enough to be worth it, and say why at the
time.
"""

import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

# --- IDENTITY ---

APP_NAME = "Minicut Shot Detector"

# Recorded in every job sidecar. When a boundary looks wrong months later, the
# first question is which version of this tool produced it.
APP_VERSION = "0.1.0"

# --- PROJECT PATHS ---

# src/core/config.py -> repo root is two parents up
REPO_ROOT = Path(__file__).resolve().parents[2]

STATIC_DIR = REPO_ROOT / "src" / "ui" / "static"

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

    # Detection settings arrive with detection, in Phase 4. Holding a threshold
    # here that nothing reads, while the detector carries its own default,
    # would be two places claiming the same fact.

    # Mezzanine & Cutting
    # The encoder is not a setting: it follows the source codec, because shots
    # come out in the format they went in as.
    #
    # Nor is keeping the mezzanine: a job that passes deletes it, and a job
    # that fails keeps it, because a failure is exactly when the intermediate
    # is worth having.

    # Validation
    # Rejoin every shot and compare every frame, rather than comparing the
    # frames either side of each cut. Both catch the failures a stream copy can
    # actually produce; the full version also takes several times longer and
    # needs room for a second copy of the mezzanine.
    full_round_trip: bool = False

    # Masking is deliberately absent: detected letterboxing is reported, never
    # applied, so there is nothing for the user to override.


# --- MODEL BACKENDS ---

# The three ways of reaching a model. The command and API paths are the
# product; local is the option, because this is handed to people whose machines
# are nothing like the one it was written on.
BACKEND_COMMAND = "command"
BACKEND_API = "api"
BACKEND_LOCAL = "local"

BACKEND_KINDS = (BACKEND_COMMAND, BACKEND_API, BACKEND_LOCAL)

# Hosted APIs agree on almost nothing: the shape of the request, where the text
# comes back, how an image is attached. The user says which dialect their
# endpoint speaks rather than us sniffing, so a mismatch is a clear message
# instead of a confusing one.
STYLE_ANTHROPIC = "anthropic"
STYLE_OPENAI = "openai"
STYLE_OLLAMA = "ollama"

API_STYLES = (STYLE_ANTHROPIC, STYLE_OPENAI, STYLE_OLLAMA)

# Ceiling on a single reply. An observation is a dozen short lines, so this is
# generous for the job and still stops a runaway answer costing real money.
MAX_REPLY_TOKENS = 2000

# Long enough for a vision model on a slow machine, short enough that a stalled
# call fails rather than hanging a forty-shot batch all afternoon.
BACKEND_TIMEOUT_SECONDS = 180

# Where local model runtimes conventionally listen.
LOCAL_ENDPOINT = "http://127.0.0.1:11434"


class BackendConfig(BaseModel):
    """
    How to reach one model backend.

    Held per pass, so the vision and text passes can point at different things —
    a studio may run every text pass through a CLI it already licenses and have
    to send image work somewhere else.

    A passive container: nothing here performs work, and no credential is ever
    stored in it. `api_key_env` names the environment variable holding the key,
    which is read at the moment of the call — a config file is the sort of
    thing that gets copied between machines and committed by accident.
    """

    kind: str = BACKEND_COMMAND            # One of BACKEND_KINDS
    model: Optional[str] = None            # Model name, where the backend takes one
    command: Optional[list] = None         # For "command": the executable and its arguments
    endpoint: Optional[str] = None         # For "api" and "local": the URL
    api_style: str = STYLE_ANTHROPIC       # Which dialect the endpoint speaks
    api_key_env: Optional[str] = None      # For "api": the variable holding the key, never the key

    timeout_seconds: int = BACKEND_TIMEOUT_SECONDS
    max_tokens: int = MAX_REPLY_TOKENS


class IdentifierConfig(BaseModel):
    """
    Settings for a single identifier run.

    The same shape as `ProjectConfig` above and for the same reason: the
    pipeline reads these values and hands them down to the stage modules, so
    there is one object to serialise when the UI saves a job setup.

    Vision and text are separate backends rather than one, because they are
    routinely different in practice and a single setting could not express that.
    """

    # Path Persistence
    shots_dir: Optional[str] = None        # The folder of single-shot files to identify
    knowledge_dir: Optional[str] = None    # Holds terminology.md and characters.md
    shot_list_path: Optional[str] = None   # CSV, text document, or a folder of thumbnails

    # Backends
    vision: BackendConfig = BackendConfig()
    text: BackendConfig = BackendConfig()

    # Re-observe shots that already have a cached description. Off by default:
    # the vision pass is the expensive step and its whole purpose is to happen
    # once, so repeating it has to be asked for.
    force_observe: bool = False


# --- SAVED SETTINGS ---

# Sits beside the app rather than in a user profile, so a facility can set one
# up once and hand the whole folder over — which is how this gets distributed.
# Gitignored, because a working file and a tracked file are different things:
# `settings.example.json` is the template that ships.
SETTINGS_FILE = REPO_ROOT / "settings.json"


class Settings(BaseModel):
    """
    What the app remembers between runs.

    Only the model backends for now. The splitter needs nothing remembered: its
    paths are chosen per job and suggesting them from the source is better than
    recalling the last one.

    Never holds a credential. `BackendConfig.api_key_env` names the environment
    variable holding a key, and this file is the exact sort of thing that gets
    copied between machines and committed by accident — which is why the key
    itself is read from the environment at the moment of the call.
    """

    vision: BackendConfig = BackendConfig()   # The observation pass — the only one with images
    text: BackendConfig = BackendConfig()     # Interpretation and matching


def load_settings(path: Optional[Path] = None) -> Settings:
    """
    Reads the settings file, or returns the defaults.

    Args:
        path: Where to read from. Defaults to `SETTINGS_FILE`.

    Returns:
        Settings: the file's contents, or defaults when there is no file.

    Notes:
        A missing file is the normal state on a fresh install, not an error —
        the splitter works with no backend configured at all, so this must not
        be the thing that stops the app opening.

        A corrupt or outdated file is also non-fatal: it is logged and the
        defaults are used. Refusing to start because one field was renamed
        would strand someone with no way back in to fix it.
    """
    target = path or SETTINGS_FILE

    if not target.is_file():
        return Settings()

    try:
        # utf-8-sig, not utf-8: Notepad and PowerShell's Set-Content both write
        # a byte order mark, and a BOM makes the file invalid JSON. Without
        # this, a Windows user edits the file, the app silently ignores it, and
        # the panel insists nothing is configured — which is the worst kind of
        # failure, because they can see the settings they just typed.
        # Harmless when there is no BOM.
        return Settings.model_validate_json(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        logging.warning(f"Ignoring unreadable settings at {target}: {error}")
        return Settings()


def save_settings(settings: Settings, path: Optional[Path] = None) -> Path:
    """
    Writes the settings file, and returns where it went.

    Raises:
        OSError: If it could not be written. Surfaced rather than swallowed —
            a save that silently did nothing is worse than one that failed.
    """
    target = path or SETTINGS_FILE
    target.write_text(settings.model_dump_json(indent=2), encoding="utf-8")

    logging.info(f"Settings written to {target}")
    return target
