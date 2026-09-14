"""
Identifier Routes.

What the Identifier tab needs that the Splitter does not. The production
knowledge folder for now; the observation, matching, rename and export routes
join it as Phase 7 fills in.
"""

import json
from mimetypes import guess_type
from pathlib import Path
from typing import Iterator, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.core.config import PRODUCTION_DIR, VIDEO_SUFFIXES, IdentifierConfig, load_settings
from src.core.models import NamingScheme, ShotRecord
from src.identifier.export import first_frame, write_csv, write_thumbnails, write_xlsx
from src.identifier.knowledge import CATEGORIES, PRODUCTION_FILE, load_knowledge
from src.identifier.pipeline import IdentifierPipeline
from src.identifier.rename import (
    apply_renames,
    check_plan,
    number_shots,
    original_name_of,
    restore_records,
    undo_renames,
)
from src.ui.runtime import toolchain

# Where a breakdown is written: beside the shots it describes, so it travels
# with the folder rather than landing somewhere only this machine knows.
EXPORT_DIR = "breakdown"

# Read size for ranged video. Large enough not to thrash on a 40MB clip, small
# enough that seeking feels immediate.
CHUNK = 1024 * 256

router = APIRouter()

# --- IDENTIFIER: PRODUCTION KNOWLEDGE ---


@router.get("/api/knowledge")
def get_knowledge():
    """
    What the production folder currently holds.

    Read fresh every time rather than cached: someone edits the file in another
    window and presses Re-check expecting it picked up, and a cache would
    quietly serve them the old one.

    Returns counts rather than contents. The panel says what was found; the
    text itself is for the model, and a show's full description would make the
    response enormous for no reason anybody can read.

    The film terminology is deliberately absent. It ships with the app, changes
    almost never, and showing it would only invite editing the one thing here
    that does not need editing.
    """
    knowledge = load_knowledge(PRODUCTION_DIR)

    return {
        "directory": str(PRODUCTION_DIR),
        "file": PRODUCTION_FILE,
        "found": knowledge.has_production,
        "counts": knowledge.counts,
        "categories": list(CATEGORIES),
    }


class DescribeRequest(BaseModel):
    """A request to describe every shot in a folder."""

    shots_dir: str

    # Re-observe shots that already have a cached description. Off by default:
    # the vision pass is the expensive step and its whole purpose is to happen
    # once, so repeating it has to be asked for.
    force: bool = False


@router.post("/api/identify/describe")
def post_describe(request: DescribeRequest) -> List[ShotRecord]:
    """
    Describes every shot in a folder and reads it in the project's terms.

    Blocking, and on a folder of forty this means minutes — one vision call per
    shot. The front end says so rather than pretending otherwise, and the
    observations are cached per shot as they land, so a second run costs
    nothing for the shots already done.

    Raises:
        HTTPException: 422 for a folder that is empty or not a folder, and 409
            when no usable model is configured — which is a setting to correct
            rather than a bad request.
    """
    config = IdentifierConfig(
        shots_dir=request.shots_dir,
        force_observe=request.force,
        vision=load_settings().vision,
        text=load_settings().text,
    )

    try:
        return IdentifierPipeline(config, toolchain).prepare()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.post("/api/identify/describe/stream")
def post_describe_stream(request: DescribeRequest) -> StreamingResponse:
    """
    The same run as `post_describe`, sending each shot back as it finishes.

    One JSON object per line, which is what the table draws a row from. A batch
    is minutes long, and a table that fills in as the work lands is the
    difference between a slow run and one that looks hung — the reason a good
    run has been killed before now.

    A POST rather than an event stream, because the folder is a path off this
    machine and has no business in a URL.

    Notes:
        The first line is an object carrying `total`, so the table knows how
        many rows to expect before any arrives. Errors that would be a status
        code on the blocking route arrive as a final `{"error": ...}` line:
        the response has already begun by the time most of them can happen.
    """
    config = IdentifierConfig(
        shots_dir=request.shots_dir,
        force_observe=request.force,
        vision=load_settings().vision,
        text=load_settings().text,
    )

    pipeline = IdentifierPipeline(config, toolchain)

    def lines() -> Iterator[str]:
        try:
            records = pipeline.shots()
            yield json.dumps({"total": len(records)}) + "\n"

            for record in pipeline.prepare_stream(records=records):
                yield record.model_dump_json() + "\n"
        except (ValueError, RuntimeError) as error:
            yield json.dumps({"error": str(error)}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


# --- IDENTIFIER: NAMING AND RENAMING ---


class NumberRequest(BaseModel):
    """A batch of reviewed shots, and the convention to number them by."""

    records: List[ShotRecord]
    scheme: NamingScheme


@router.post("/api/identify/number")
def post_number(request: NumberRequest) -> List[ShotRecord]:
    """
    Proposes a name for every shot from the production's own convention.

    Nothing is written. This fills the shot number column so the whole batch
    can be read and corrected before a single file is touched — the naming
    convention is the kind of thing that is wrong in a way you only see laid
    out over forty rows.
    """
    return number_shots(request.records, request.scheme)


class RenameRequest(BaseModel):
    """The shots to rename, and the folder they live in."""

    records: List[ShotRecord]
    shots_dir: str


@router.post("/api/identify/rename/check")
def post_rename_check(request: RenameRequest) -> dict:
    """
    What would go wrong, before anything happens.

    Returns:
        `{"problems": [...]}` — empty when the plan is safe. Shown rather than
        raised: this is the step whose whole purpose is to be read.
    """
    return {"problems": check_plan(request.records)}


@router.post("/api/identify/rename")
def post_rename(request: RenameRequest) -> List[ShotRecord]:
    """
    Renames the approved files, reversibly.

    The only destructive route in the app. The plan is re-checked here rather
    than trusted from the check call, because files can change under a user who
    left the tab open.

    Raises:
        HTTPException: 409 when the plan is unsafe, naming every problem. Not
            422: the request is well formed, the folder is not what it was.
    """
    try:
        return apply_renames(request.records, Path(request.shots_dir))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.post("/api/identify/rename/undo")
def post_rename_undo(request: RenameRequest) -> dict:
    """
    Puts a renamed batch back, and hands the table rows that match the folder.

    Returns:
        How many files moved, and the records pointing at the names that are
        now on disk. Without the records the table keeps the renamed paths
        after the files have gone back, so every row points at something that
        is not there — the clips stop playing and the names read wrong, which
        is worse than the state the undo was meant to recover.
    """
    directory = Path(request.shots_dir)
    restored = undo_renames(directory)

    return {
        "restored": restored,
        "records": restore_records(request.records, directory),
    }


# --- IDENTIFIER: EXPORT ---


class ExportRequest(BaseModel):
    """What to write, where, and whether to bring the stills."""

    records: List[ShotRecord]
    shots_dir: str
    thumbnails: bool = True


@router.post("/api/identify/export")
def post_export(request: ExportRequest) -> dict:
    """
    Writes the breakdown beside the shots.

    Both formats every time: CSV for a tracker to import, .xlsx for a person to
    open and send on. Writing one and not the other only means coming back for
    the second at the moment it is wanted.

    Returns:
        The folder written, the two files, and how many thumbnails went with
        them.
    """
    output_dir = Path(request.shots_dir) / EXPORT_DIR

    try:
        csv_path = write_csv(request.records, output_dir)
        xlsx_path = write_xlsx(request.records, output_dir)
    except OSError as error:
        raise HTTPException(status_code=422, detail=f"Could not write the export: {error}")

    stills = write_thumbnails(request.records, output_dir) if request.thumbnails else []

    return {
        "folder": str(output_dir),
        "csv": csv_path.name,
        "xlsx": xlsx_path.name,
        "thumbnails": len(stills),
    }


# --- IDENTIFIER: SERVING THE SHOTS THEMSELVES ---


def _safe_media(path: str, suffixes) -> Path:
    """
    Resolves a requested file, or refuses it.

    The table asks for clips and stills by path, which is a door worth keeping
    narrow even on an app bound to localhost: the answer is a real file of an
    expected kind, or a 404 that says nothing about what else is on the disk.

    Raises:
        HTTPException: 404 for anything missing, not a file, or not one of the
            expected extensions.
    """
    target = Path(path).resolve()

    if not target.is_file() or target.suffix.lower() not in suffixes:
        raise HTTPException(status_code=404, detail="No such file")

    return target


@router.get("/api/identify/clip")
def get_clip(path: str, request: Request):
    """
    Serves one shot for playback in the review table.

    Answers range requests, because a reviewer scrubs a clip rather than
    watching it from the top — and a browser given a whole file with no range
    support can play it but cannot seek in it.

    Notes:
        The table sets `preload="none"`, so nothing here runs until someone
        presses play on a row. A forty row table costs no video traffic at all
        until it is asked for.
    """
    target = _safe_media(path, VIDEO_SUFFIXES)
    size = target.stat().st_size
    media_type = guess_type(target.name)[0] or "video/mp4"

    span = request.headers.get("range")
    if not span:
        return FileResponse(target, media_type=media_type)

    start, end = _range_of(span, size)
    length = end - start + 1

    def chunk() -> Iterator[bytes]:
        with open(target, "rb") as handle:
            handle.seek(start)
            remaining = length

            while remaining > 0:
                block = handle.read(min(CHUNK, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block

    return StreamingResponse(
        chunk(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


def _range_of(header: str, size: int) -> tuple:
    """
    The byte span a browser asked for, clamped to the file.

    Args:
        header: The raw `Range` header, in the only form browsers send it.
        size: The file's length.

    Returns:
        `(start, end)`, both inclusive, always inside the file.

    Notes:
        Anything unparseable is treated as a request for the whole file rather
        than refused. A malformed range is a browser quirk, not an attack, and
        serving the file is a better answer than a 416 nobody can act on.
    """
    try:
        span = header.split("=", 1)[1]
        first, _, last = span.partition("-")

        start = int(first) if first else 0
        end = int(last) if last else size - 1
    except (IndexError, ValueError):
        return 0, size - 1

    start = max(0, min(start, size - 1))
    end = max(start, min(end, size - 1))

    return start, end


@router.get("/api/identify/poster")
def get_poster(path: str):
    """
    The still a row shows before anyone presses play.

    The frame the vision pass already sampled, so a table of forty posters
    costs no decoding at all.

    Raises:
        HTTPException: 404 where the frames have been cleared away. The row
            simply has no poster then, which the table handles.
    """
    target = Path(path)

    # Frames are written from the stem a shot had when it was described and
    # stay there after a rename, so a poster asked for by the new name finds
    # nothing. The log is what maps one back to the other — without this the
    # whole table turns grey the moment it is renamed.
    record = ShotRecord(
        file=path,
        original_file=original_name_of(target.parent, target.name),
    )
    frame = first_frame(record)

    if frame is None:
        raise HTTPException(status_code=404, detail="No sampled frame")

    return FileResponse(frame, media_type="image/jpeg")
