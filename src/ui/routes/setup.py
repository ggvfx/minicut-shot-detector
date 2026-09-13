"""
Setup Routes.

What is installed, how to install it, and which model each pass talks to.
Everything the Setup tab shows, plus the model picker the Identifier carries.
"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.backends.adapter import BackendError, create_backend
from src.backends.availability import backend_checks
from src.core.config import (
    BACKEND_COMMAND,
    CLI_PRESETS,
    MIN_PYTHON,
    SETTINGS_FILE,
    BackendConfig,
    Settings,
    load_settings,
    save_settings,
)
from src.core.environment import (
    IDENTIFIER,
    SPLITTER,
    TABS,
    ffmpeg_fixes,
    platform_name,
    python_fixes,
)
from src.ui.runtime import checker

router = APIRouter()

# --- ENVIRONMENT ---


@router.get("/api/environment")
def get_environment(
    tab: str = SPLITTER, output_dir: Optional[str] = None, refresh: bool = False
):
    """
    The dependency panel for one tab.

    Args:
        tab: "splitter" or "identifier". Each is told what it needs and nothing
            else — the splitter needs encoders and PySceneDetect, the
            identifier needs a model, and neither can act on the other's
            requirements.
        output_dir: Chosen output directory, so free space is checked against
            the volume that will actually be written to.
        refresh: True when the user presses Re-check. Otherwise the cached
            result is returned, since the checks shell out to ffmpeg.

    Notes:
        The backend rows are assembled here rather than inside the checker,
        because they come from `src/backends/` and core may not import a domain
        package. This route may import both, so this is where they meet.

        They appear only in the identifier panel, and they gate it: a user
        standing in that tab with no model cannot do anything, and should be
        told so plainly. The splitter never sees them.
    """
    if tab not in TABS:
        raise HTTPException(status_code=422, detail=f"Unknown tab {tab!r}")

    target = Path(output_dir) if output_dir else None
    extra = backend_checks(load_settings()) if tab == IDENTIFIER else None

    return checker.report(tab, target, refresh=refresh, extra=extra)


# --- SETUP GUIDE ---


@router.get("/api/guide")
def get_guide():
    """
    How to install what the app needs, whatever state the machine is in.

    Separate from the environment checks on purpose. Those only speak up when
    something is missing, which is right for a status panel and useless for
    someone setting up a second machine, or checking what a colleague will
    need before sending them the folder.

    Only this platform's instructions: the app knows which it is on, and a
    Windows user scrolling past Homebrew is noise.
    """
    return {
        "platform": platform_name(),
        "python": {
            "label": f"Python {'.'.join(str(part) for part in MIN_PYTHON)} or newer",
            "fixes": [step.model_dump() for step in python_fixes()],
        },
        "ffmpeg": {
            "label": "ffmpeg and ffprobe",
            "fixes": [step.model_dump() for step in ffmpeg_fixes()],
        },
    }


# --- IDENTIFIER: MODEL BACKENDS ---


class BackendChoice(BaseModel):
    """One pass's backend, as the settings panel sends it."""

    preset: str = "claude"                 # A key from CLI_PRESETS
    command: Optional[List[str]] = None    # Only used when preset is "custom"


class SettingsRequest(BaseModel):
    """Both passes, saved together — they are always shown together."""

    vision: BackendChoice
    text: BackendChoice


@router.get("/api/settings")
def get_settings():
    """
    The configured backends, and the presets available to choose from.

    Sends the presets alongside so the panel is built from one source rather
    than from a list in the front end that would drift from this one.
    """
    settings = load_settings()

    return {
        "presets": [
            {"key": key, "label": preset["label"], "note": preset["note"]}
            for key, preset in CLI_PRESETS.items()
        ],
        "vision": _describe_choice(settings.vision),
        "text": _describe_choice(settings.text),
    }


def _describe_choice(config: BackendConfig) -> dict:
    """
    Which preset a saved config corresponds to, for the dropdown.

    Matching on the command rather than storing the preset name: the command is
    the thing that actually runs, and a stored name could disagree with it
    after someone edits settings.json by hand.
    """
    command = config.command or []

    for key, preset in CLI_PRESETS.items():
        if key != "custom" and preset["command"] == command:
            return {"preset": key, "command": command}

    return {"preset": "custom", "command": command}


@router.post("/api/settings")
def post_settings(request: SettingsRequest):
    """
    Saves both backends.

    Notes:
        Written whether or not the command works. Someone setting up a tool
        they have not installed yet should be able to save it and come back —
        the panel already reports what is reachable, so refusing to save would
        just mean losing their typing.
    """
    settings = Settings(
        vision=_build_config(request.vision),
        text=_build_config(request.text),
    )
    save_settings(settings)

    return {"saved": True, "path": str(SETTINGS_FILE)}


def _build_config(choice: BackendChoice) -> BackendConfig:
    """
    Turns a dropdown choice into a backend config.

    Raises:
        HTTPException: If the preset is not one this app offers.
    """
    if choice.preset not in CLI_PRESETS:
        raise HTTPException(status_code=422, detail=f"Unknown preset {choice.preset!r}")

    preset = CLI_PRESETS[choice.preset]
    command = choice.command if choice.preset == "custom" else preset["command"]

    return BackendConfig(
        kind=BACKEND_COMMAND,
        command=[part for part in (command or []) if part],
        image_reference=preset.get("image_reference"),
    )


@router.post("/api/backends/test")
def post_backend_test(choice: BackendChoice):
    """
    Runs a backend once and reports what came back.

    This is what makes the panel usable by someone who does not work in a
    terminal. A dropdown and a Save button can only promise; pressing Test
    either shows the model's own words or says exactly what went wrong, which
    is the difference between setting this up and giving up on it.

    Notes:
        Deliberately a tiny prompt. It proves the tool runs, is authenticated
        and answers — which is everything the panel needs to know — without
        spending anything worth counting.
    """
    backend = create_backend(_build_config(choice))

    try:
        reply = backend.send("Reply with the single word: ready")
    except BackendError as error:
        return {"ok": False, "detail": str(error)}

    return {
        "ok": True,
        "detail": reply.text.strip()[:200],
        "seconds": reply.seconds,
        "backend": reply.backend,
    }
