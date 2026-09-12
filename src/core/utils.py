"""
Shared Utility Functions.

Small helpers used across more than one module. Anything here must depend on
nothing but the standard library — this is the bottom of the dependency chain.

If a helper is only used by one module, it belongs in that module instead.
"""

import hashlib
from pathlib import Path

# --- FILE HELPERS ---


def file_sha256(path: Path) -> str:
    """
    Checksum of a file.

    Read in blocks rather than all at once, so checksumming the model does not
    pull a hundred megabytes into memory.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_directory(path: Path) -> Path:
    """
    Creates a directory if it does not exist, and returns it.

    Used before writing splits and sidecars, so a missing output folder
    is never the reason a job fails halfway through.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
