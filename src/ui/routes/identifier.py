"""
Identifier Routes.

What the Identifier tab needs that the Splitter does not. The production
knowledge folder for now; the observation, matching, rename and export routes
join it as Phase 7 fills in.
"""

from fastapi import APIRouter

from src.core.config import PRODUCTION_DIR
from src.identifier.knowledge import CATEGORIES, PRODUCTION_FILE, load_knowledge

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
