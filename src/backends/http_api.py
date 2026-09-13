"""
HTTP API Backend.

For people with a key and no wish to run anything locally. Plain HTTP against a
configured endpoint — no vendor SDK, for the same reason the splitter shells
out to ffmpeg rather than importing a binding: one fewer dependency to pin, and
nothing that breaks when a library reorganises itself.
"""

import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from src.backends.adapter import (
    STYLE_ANTHROPIC,
    STYLE_OPENAI,
    BackendConfig,
    BackendError,
    ModelBackend,
    ModelReply,
    build_request,
    extract_text,
    read_images,
)
from src.backends.transport import post_json

# --- HEADERS ---

# The version header Anthropic's API requires. Pinned rather than floating for
# the same reason as everything in requirements.txt: an API that changes shape
# under us should be a deliberate upgrade, not a surprise on a Tuesday.
ANTHROPIC_VERSION = "2023-06-01"


class HttpApiBackend(ModelBackend):
    """
    Sends prompts to an HTTP endpoint.

    The key is read from the environment variable the config names, at the
    moment of the call. It is never held in the config object, written to a
    settings file, logged, or returned in an error — a config file is the sort
    of thing that gets copied between machines and committed by accident.
    """

    def __init__(self, config: BackendConfig):
        super().__init__(config)

    # --- SENDING ---

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        """
        Posts the prompt and any images, and returns the text.

        Raises:
            BackendError: On a missing key, a transport failure, a non-success
                status, or a body without text where this dialect puts it. The
                message says which of those happened and never quotes the key.
        """
        if not self.config.endpoint:
            raise BackendError("No endpoint is configured for this backend")

        key = self._read_key()
        body = build_request(prompt, read_images(images), self.config)

        started = time.monotonic()
        payload = post_json(
            self.config.endpoint,
            body,
            self._headers(key),
            self.config.timeout_seconds,
        )

        return ModelReply(
            text=extract_text(payload, self.config.api_style),
            backend=f"api:{self.config.api_style}",
            model=self.config.model,
            seconds=round(time.monotonic() - started, 2),
        )

    def _read_key(self) -> str:
        """
        Reads the key from the environment at call time.

        Raises:
            BackendError: If the variable is unset or empty, naming the
                variable — never the value. Someone reading this error over a
                shoulder should learn what to set, not what it is set to.
        """
        if not self.config.api_key_env:
            raise BackendError(
                "No API key variable is configured. Set api_key_env to the name "
                "of the environment variable holding the key."
            )

        key = os.environ.get(self.config.api_key_env, "").strip()
        if not key:
            raise BackendError(
                f"The environment variable {self.config.api_key_env} is not set. "
                f"Set it to your API key and re-check the environment."
            )

        return key

    def _headers(self, key: str) -> Dict[str, str]:
        """
        Auth headers for the configured dialect.

        Built per call and never stored, so the key exists only for the length
        of one request.
        """
        if self.config.api_style == STYLE_ANTHROPIC:
            return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}

        if self.config.api_style == STYLE_OPENAI:
            return {"Authorization": f"Bearer {key}"}

        # A local-style endpoint reached over the network takes no credential
        return {}

    # --- AVAILABILITY ---

    def available(self) -> bool:
        """
        Whether an endpoint is configured and its key is present.

        Deliberately does not call the endpoint. The environment panel asks on
        every refresh, and a check that cost a token each time would be a
        running charge for looking at a status light.
        """
        if not self.config.endpoint or not self.config.api_key_env:
            return False

        return bool(os.environ.get(self.config.api_key_env, "").strip())

    def describe(self) -> str:
        """A short line naming this backend, for the panel and the sidecar."""
        return f"api:{self.config.api_style}:{self.config.model or 'default'}"
