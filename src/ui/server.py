"""
FastAPI Server and Routes.

The only module that knows about HTTP. Routes translate a request into a call
into the pipeline or a core module, and translate the result back to JSON.

No processing logic lives here — if a route grows a decision in it, that
decision belongs in a stage module instead.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.core.config import STATIC_DIR
from src.core.environment import EnvironmentChecker
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import ProbeReport
from src.media.probe import SourceProbe
from src.ui import browse

app = FastAPI(title="Minicut Shot Detector")

# One toolchain and one checker for the life of the process, so ffmpeg is
# discovered once and the environment report is cached between panel refreshes.
toolchain = MediaToolchain()
checker = EnvironmentChecker(toolchain)


# --- REQUEST BODIES ---


class ProbeRequest(BaseModel):
    """A request to inspect a source before starting a job."""

    source_path: str
    output_dir: Optional[str] = None

# --- PAGE ---


@app.get("/")
def index():
    """Serves the single page app."""
    return FileResponse(STATIC_DIR / "index.html")


# --- ENVIRONMENT ---


@app.get("/api/environment")
def get_environment(output_dir: Optional[str] = None, refresh: bool = False):
    """
    The dependency panel.

    Args:
        output_dir: Chosen output directory, so writability and free space are
            checked against the volume that will actually be written to.
        refresh: True when the user presses Re-check. Otherwise the cached
            result is returned, since the checks shell out to ffmpeg.
    """
    target = Path(output_dir) if output_dir else None
    return checker.report(target, refresh=refresh)


# --- FILE BROWSING ---


@app.get("/api/browse")
def get_directory(path: Optional[str] = None, videos_only: bool = False):
    """
    Lists a directory for the path picker.

    Args:
        path: Directory to list. Defaults to the user's home folder.
        videos_only: Hide non-video files, for the source picker.
    """
    target = Path(path) if path else Path.home()

    try:
        return browse.list_directory(target, videos_only=videos_only)
    except NotADirectoryError:
        raise HTTPException(status_code=404, detail=f"Not a directory: {target}")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {target}")


# --- SOURCE INSPECTION ---


@app.post("/api/probe")
def post_probe(request: ProbeRequest) -> ProbeReport:
    """
    Inspects a source: metadata, masking, and the disk the job would need.

    Runs cropdetect over several samples, so this takes a moment on a long
    file. It stays a plain blocking call until there is a job to stream
    progress for.
    """
    source_path = Path(request.source_path)
    output_dir = Path(request.output_dir) if request.output_dir else None

    try:
        return SourceProbe(toolchain).inspect(source_path, output_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_path}")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


# --- JOBS (NOT BUILT YET) ---

# Phase 3 onwards adds:
#   POST /api/job               start a splitter run, return a job id
#   GET  /api/job/{id}/events   SSE progress stream for that run
#
# Long operations must never block a request — the UI has to stay responsive
# while a transcode runs.


# --- STATIC FILES ---

# Mounted last so it cannot shadow the API routes above.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
