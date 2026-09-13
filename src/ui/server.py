"""
The App.

Creates the FastAPI app, serves the page, mounts the static files, and wires in
the routers. Nothing else — this is the assembly, not the work.

The routes themselves live in `src/ui/routes/`, one module per tab, mirroring
`src/splitter/` and `src/identifier/` so that a reader who has learned where
the splitter's code lives already knows where its routes live.
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import STATIC_DIR
from src.ui.routes import files, identifier, setup, splitter

app = FastAPI(title="Minicut Shot Detector")

# --- ROUTES ---

# Setup first, because it is what a machine with nothing installed needs.
app.include_router(setup.router)
app.include_router(splitter.router)
app.include_router(identifier.router)
app.include_router(files.router)


# --- PAGE ---


# --- PAGE ---


@app.get("/")
def index():
    """Serves the single page app."""
    return FileResponse(STATIC_DIR / "index.html")


# --- STATIC FILES ---


class RevalidatedStatics(StaticFiles):
    """
    Static files the browser must re-check before reusing.

    Without a Cache-Control header a browser caches by its own heuristic, and an
    ES module it has already evaluated stays in the module map even across a
    reload. The result is that someone updates the app, opens it, and gets
    yesterday's JavaScript — which looks like the new feature simply not
    working, with nothing on screen to say why. It cost an hour of this build
    before it was spotted.

    `no-cache` does not mean "do not store": it means "ask before reusing".
    With the ETag the server already sends, an unchanged file costs one 304 and
    no body, which on localhost is free.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Mounted last so it cannot shadow the API routes above.
app.mount("/static", RevalidatedStatics(directory=STATIC_DIR), name="static")
