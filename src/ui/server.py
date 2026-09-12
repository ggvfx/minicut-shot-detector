"""
FastAPI Server and Routes.

The only module that knows about HTTP. Routes translate a request into a call
into the pipeline or a core module, and translate the result back to JSON.

No processing logic lives here — if a route grows a decision in it, that
decision belongs in a stage module instead.
"""

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.core.config import STATIC_DIR, ProjectConfig
from src.core.environment import EnvironmentChecker
from src.core.ffmpeg_tools import MediaToolchain
from src.core.models import Boundary, JobResult, PreparedJob, ProbeReport
from src.core.timecode import Timecode
from src.media.probe import SourceProbe
from src.media.proxy import PROXY_SUFFIX
from src.pipeline import SplitterPipeline
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


class SplitRequest(BaseModel):
    """A request to split a source on hand-typed boundaries."""

    source_path: str
    output_dir: str

    # Each entry is a frame number or a timecode, as typed. Interpreted against
    # the source's own frame rate, so the two cannot be confused.
    boundaries: List[str] = []

    # Rejoin every shot and compare every frame, rather than comparing the
    # frames either side of each cut.
    full_round_trip: bool = False

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


# --- PREPARING FOR REVIEW ---


@app.post("/api/analyse")
def post_analyse(request: ProbeRequest) -> PreparedJob:
    """
    Gets a source ready for its cuts to be reviewed.

    Builds the mezzanine and the small proxy the player scrubs through. This is
    the slow call — the encode happens here rather than at split time, so
    adjusting boundaries costs nothing and cutting afterwards is quick.

    Blocking, like the split. Streaming progress is Phase 5.
    """
    if not request.output_dir:
        raise HTTPException(status_code=422, detail="Choose an output directory first")

    config = ProjectConfig(source_path=request.source_path, output_dir=request.output_dir)

    try:
        return SplitterPipeline(config, toolchain).prepare()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Source not found: {request.source_path}")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))


@app.get("/api/proxy")
def get_proxy(path: str):
    """
    Serves a review proxy for the player.

    Range requests are what let the browser seek without downloading the whole
    file first, and FileResponse handles them.

    Only proxies are served, never arbitrary media: the player has no business
    reading anything else, and neither does anyone who finds this endpoint.
    """
    proxy_path = Path(path)

    if not proxy_path.name.endswith(PROXY_SUFFIX):
        raise HTTPException(status_code=403, detail="Only review proxies can be served")
    if not proxy_path.is_file():
        raise HTTPException(status_code=404, detail=f"No proxy at {proxy_path}")

    return FileResponse(proxy_path, media_type="video/mp4")


# --- SPLITTING ---


@app.post("/api/split")
def post_split(request: SplitRequest) -> JobResult:
    """
    Splits a source on the given boundaries and returns the finished job.

    Blocking, and on a long source that means minutes. Streaming progress is
    Phase 5; until then the front end says so rather than pretending otherwise.

    Boundaries arrive as typed text and are read against the source's own frame
    rate, so "1247" and "01:00:51:23" both work and cannot be confused.
    """
    source_path = Path(request.source_path)
    config = ProjectConfig(
        source_path=request.source_path,
        output_dir=request.output_dir,
        full_round_trip=request.full_round_trip,
    )

    try:
        source = SourceProbe(toolchain).probe(source_path)
        timecode = Timecode.from_source(source)
        boundaries = [
            Boundary(frame=timecode.parse_frame_reference(value))
            for value in request.boundaries
            if value.strip()
        ]

        return SplitterPipeline(config, toolchain).run(boundaries)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_path}")
    except ValueError as error:
        # A bad boundary or a missing setting: the user can fix both
        raise HTTPException(status_code=422, detail=str(error))
    except RuntimeError as error:
        # A refused source, or a stage that could not complete
        raise HTTPException(status_code=409, detail=str(error))


# --- PROGRESS (NOT BUILT YET) ---

# Phase 5 adds SSE progress for a running job, so a long split does not sit
# behind a blocking request with nothing to show for it.


# --- STATIC FILES ---

# Mounted last so it cannot shadow the API routes above.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
