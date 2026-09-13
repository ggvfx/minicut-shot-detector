"""
The Backend Interface.

One method, because one method is all the identifier needs: give it a prompt
and possibly some images, get text back. Everything that makes backends differ
— a subprocess, an HTTP request, a local runtime — stays behind it.

Keeping the interface this narrow is what lets a studio point the text passes
at one thing and the vision pass at another without a line of identifier code
knowing about it.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

# --- CONFIGURATION ---


class BackendConfig(BaseModel):
    """
    How to reach one backend.

    Stored per pass, so `vision` and `text` can point at different things.

    Attributes:
        kind: "command", "api" or "local".
        model: Model name, where the backend takes one.
        command: For "command" — the executable and its arguments.
        endpoint: For "api" — the URL.
        api_key_env: For "api" — the environment variable holding the key.
            The key itself is never stored here or written to disk: a config
            file that travels between machines must not carry a credential.
        timeout_seconds: How long one call may take before it is abandoned.
    """

    kind: str
    model: Optional[str] = None
    command: Optional[List[str]] = None
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None
    timeout_seconds: int = 180


class ModelReply(BaseModel):
    """
    What came back, and what produced it.

    The backend and model are recorded alongside the text for the same reason
    the splitter's sidecar records the ffmpeg build: when an answer looks wrong
    weeks later, the first question is what produced it. Unlike the splitter,
    the same input here can give a different answer twice, which makes the
    record more important rather than less.
    """

    text: str
    backend: str
    model: Optional[str] = None
    seconds: float = 0.0


# --- THE INTERFACE ---


class ModelBackend:
    """
    Base class for every backend.

    Subclasses implement `send` and nothing else. A backend does not know what
    an observation is, what a shot list is, or which pass called it — it takes
    text and images and returns text.
    """

    def __init__(self, config: BackendConfig):
        self.config = config

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        """
        Sends one prompt, with optional images, and returns what came back.

        Args:
            prompt: The instruction and any text context.
            images: Frame files to attach. Small by design — a few hundred
                pixels, from the same ffmpeg machinery as the review proxy.
                Nothing about judging framing needs full resolution, and small
                frames keep API calls cheap, local inference quick, and fit
                CLI tools that only accept preview-sized images.

        Returns:
            ModelReply: the text, and what produced it.

        Raises:
            BackendError: If the backend could not be reached, refused the
                request, or timed out. Callers surface this rather than
                retrying blindly — a batch of forty shots must not quietly
                become forty failed calls.
        """
        raise NotImplementedError

    def available(self) -> bool:
        """
        Whether this backend can be used right now.

        Checked by the environment panel, which must report a machine with no
        GPU and a configured command as ready. Missing local inference is not
        a fault; having no working backend at all is.
        """
        raise NotImplementedError


class BackendError(RuntimeError):
    """A backend could not be reached, refused the request, or timed out."""
