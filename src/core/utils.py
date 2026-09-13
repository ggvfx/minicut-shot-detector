"""
Shared Utility Functions.

Small helpers used across more than one module. Anything here must depend on
nothing but the standard library — this is the bottom of the dependency chain.

If a helper is only used by one module, it belongs in that module instead.
"""

from pathlib import Path

# --- FILE HELPERS ---


def ensure_directory(path: Path) -> Path:
    """
    Creates a directory if it does not exist, and returns it.

    Used before writing splits and sidecars, so a missing output folder
    is never the reason a job fails halfway through.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
