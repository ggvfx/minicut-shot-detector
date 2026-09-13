"""
The Backend Interface.

One method, because one method is all the identifier needs: give it a prompt
and possibly some images, get text back. Everything that makes backends differ
— a subprocess, an HTTP request, a local runtime — stays behind it.

Keeping the interface this narrow is what lets a studio point the text passes
at one thing and the vision pass at another without a line of identifier code
knowing about it.
"""

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import (
    API_STYLES,
    BACKEND_API,
    BACKEND_COMMAND,
    BACKEND_KINDS,
    BACKEND_LOCAL,
    STYLE_ANTHROPIC,
    STYLE_OLLAMA,
    STYLE_OPENAI,
    BackendConfig,
)
from src.core.models import ModelReply

class BackendError(RuntimeError):
    """
    A backend could not be reached, refused the request, or timed out.

    Raised rather than returned empty. A pass that silently produced nothing
    would read downstream as a shot with no description, which looks like an
    unidentifiable shot rather than a broken backend — and that is the kind of
    confusion that costs an afternoon.
    """


# --- THE INTERFACE ---


class ModelBackend:
    """
    Base class for every backend.

    Subclasses implement `send` and `available` and nothing else. A backend does
    not know what an observation is, what a shot list is, or which pass called
    it — it takes text and images and returns text.
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

        Must be cheap: the panel asks on every refresh, so this may not send a
        prompt, and may not cost money.
        """
        raise NotImplementedError

    def describe(self) -> str:
        """A short line naming this backend, for the panel and the sidecar."""
        return f"{self.config.kind}:{self.config.model or 'default'}"


# --- SHARED HELPERS ---


def read_images(images: Optional[List[Path]]) -> List[str]:
    """
    Reads image files as base64, in the order given.

    Order is the only motion information the observation pass has — frames are
    sampled across a shot and read as a sequence — so it is preserved exactly
    and never sorted.

    Raises:
        BackendError: If an image is missing or unreadable. Failing here names
            the file; letting it through produces a rejected request whose
            error says nothing about which frame was at fault.
    """
    if not images:
        return []

    encoded = []
    for path in images:
        try:
            encoded.append(base64.b64encode(path.read_bytes()).decode("ascii"))
        except OSError as error:
            raise BackendError(f"Could not read the frame {path}: {error}") from error

    return encoded


def extract_text(payload: Dict[str, Any], style: str) -> str:
    """
    Pulls the reply text out of a response body.

    Args:
        payload: The decoded JSON response.
        style: Which dialect it should be in.

    Raises:
        BackendError: If there is no text where this dialect puts it. The
            message includes the keys that were present, because the usual
            cause is an endpoint speaking a different dialect than configured
            — and that is a one-line fix once you can see it.
    """
    try:
        if style == STYLE_ANTHROPIC:
            blocks = payload.get("content") or []
            text = "".join(block.get("text", "") for block in blocks)
        elif style == STYLE_OPENAI:
            choices = payload.get("choices") or []
            text = choices[0]["message"]["content"] if choices else ""
        elif style == STYLE_OLLAMA:
            text = payload.get("response") or payload.get("message", {}).get("content", "")
        else:
            raise BackendError(f"Unknown API style {style!r}; expected one of {API_STYLES}")
    except (KeyError, IndexError, AttributeError, TypeError) as error:
        raise BackendError(
            f"Could not read a {style} reply: {error}. "
            f"The response held: {sorted(payload)}"
        ) from error

    if not text.strip():
        raise BackendError(
            f"The backend returned no text. The response held: {sorted(payload)}"
        )

    return text


def build_request(prompt: str, encoded_images: List[str], config: BackendConfig) -> Dict[str, Any]:
    """
    Builds the request body for the configured dialect.

    Notes:
        Images are attached as base64 rather than by URL. These are local
        frames on someone's machine; uploading them somewhere to get a URL
        first would mean the media leaves the building twice, and for
        unreleased material once is already a question worth asking.
    """
    if config.api_style == STYLE_ANTHROPIC:
        content: List[Dict[str, Any]] = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
            }
            for data in encoded_images
        ]
        content.append({"type": "text", "text": prompt})
        return {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [{"role": "user", "content": content}],
        }

    if config.api_style == STYLE_OPENAI:
        parts: List[Dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}
            for data in encoded_images
        ]
        parts.append({"type": "text", "text": prompt})
        return {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [{"role": "user", "content": parts}],
        }

    if config.api_style == STYLE_OLLAMA:
        body: Dict[str, Any] = {
            "model": config.model,
            "prompt": prompt,
            "stream": False,
        }
        if encoded_images:
            body["images"] = encoded_images
        return body

    raise BackendError(f"Unknown API style {config.api_style!r}; expected one of {API_STYLES}")


# --- CONSTRUCTION ---


def create_backend(config: BackendConfig) -> ModelBackend:
    """
    Builds the backend a config describes.

    Imported here rather than at module level so that choosing one backend
    never imports the others' dependencies.

    Raises:
        BackendError: If the kind is not one this project has.
    """
    if config.kind == BACKEND_COMMAND:
        from src.backends.command import CommandBackend

        return CommandBackend(config)

    if config.kind == BACKEND_API:
        from src.backends.http_api import HttpApiBackend

        return HttpApiBackend(config)

    if config.kind == BACKEND_LOCAL:
        from src.backends.local import LocalBackend

        return LocalBackend(config)

    raise BackendError(f"Unknown backend kind {config.kind!r}; expected one of {BACKEND_KINDS}")


def first_available(configs: List[BackendConfig]) -> Optional[ModelBackend]:
    """
    The first configured backend that can actually be used.

    Returns:
        A usable backend, or None when none is. None is the honest answer on a
        machine where nothing has been set up yet, and is what the environment
        panel reports as blocked.
    """
    for config in configs:
        try:
            backend = create_backend(config)
        except BackendError as error:
            logging.warning(f"Skipping a backend that could not be built: {error}")
            continue

        if backend.available():
            return backend

    return None
