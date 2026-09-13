"""
Identifier Routes.

What the Identifier tab needs that the Splitter does not. The production
knowledge folder for now; the observation, matching, rename and export routes
join it as Phase 7 fills in.
"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.config import PRODUCTION_DIR, IdentifierConfig, load_settings
from src.core.models import ShotRecord
from src.identifier.knowledge import CATEGORIES, PRODUCTION_FILE, load_knowledge
from src.identifier.pipeline import IdentifierPipeline
from src.ui.runtime import toolchain

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
