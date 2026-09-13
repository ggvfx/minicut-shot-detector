"""
File Browsing.

The path picker, used by both tabs. Server-side rather than a browser file
dialog, because the media and the app are on one machine and a multi-gigabyte
source should never be uploaded to reach a server that could have opened it.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.ui import browse

router = APIRouter()

# --- FILE BROWSING ---


@router.get("/api/browse")
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
