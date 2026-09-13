"""
Local Backend.

For the minority with the hardware. A local runtime serving models over HTTP on
the machine itself — no key, no per-call cost, and nothing leaves the building,
which matters for unreleased material.

**This is the option, never the requirement.** No model file is committed here,
downloaded on first run, or needed for the app to work. The smallest useful
local vision model is around 1.7 GB; that is a download, a version to track and
a thing to go wrong, and the arrangement was already built and deleted once
when the TransNetV2 export lived in `models/`.

An unreachable local runtime is therefore not a fault. The environment panel
reports it as an option that is not in use.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

from src.backends.adapter import (
    OLLAMA,
    BackendConfig,
    BackendError,
    ModelBackend,
    ModelReply,
    build_request,
    extract_text,
    read_images,
)
from src.backends.transport import post_json

# --- DEFAULTS ---

# Where local runtimes conventionally listen. Configurable, because someone
# will run it on another machine on their own network.
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"

GENERATE_PATH = "/api/generate"
TAGS_PATH = "/api/tags"

# Short, because this decides whether a status light is green. A runtime that
# is not running refuses the connection immediately; one that is, answers a
# model list in milliseconds. Anything slower is not worth blocking the panel.
AVAILABILITY_TIMEOUT = 2.0


class LocalBackend(ModelBackend):
    """
    Sends prompts to a local model runtime.

    Same shape as the HTTP backend and deliberately not merged with it: this
    one has no credential, different failure modes (a model that is not pulled
    rather than a key that is wrong), and different advice to give when it
    fails.
    """

    def __init__(self, config: BackendConfig):
        super().__init__(config)

    # --- SENDING ---

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        """
        Posts the prompt and any images to the local runtime.

        Raises:
            BackendError: If the runtime is not running, or the configured
                model is not pulled. Both are fixable by the user in one
                command, so the message carries that command — the same
                approach as the splitter's dependency panel, where every
                blocked check comes with the line that fixes it.
        """
        # A local runtime speaks its own dialect whatever the config says, so
        # this is not left to be configured wrongly
        config = self.config.model_copy(update={"api_style": OLLAMA})
        body = build_request(prompt, read_images(images), config)

        started = time.monotonic()

        try:
            payload = post_json(self._url(GENERATE_PATH), body, {}, self.config.timeout_seconds)
        except BackendError as error:
            raise self._explain(error) from error

        return ModelReply(
            text=extract_text(payload, OLLAMA),
            backend="local",
            model=self.config.model,
            seconds=round(time.monotonic() - started, 2),
        )

    def _explain(self, error: BackendError) -> BackendError:
        """
        Turns a transport failure into advice.

        The two ways this fails are both one command away from fixed, and
        saying which command is the difference between a dead end and a
        twenty-second detour.
        """
        message = str(error)

        if "Could not reach" in message:
            return BackendError(
                f"No local model runtime is answering at {self._base()}. "
                f"Start it with 'ollama serve', or use a CLI or API backend instead."
            )

        if "404" in message or "not found" in message.lower():
            return BackendError(
                f"The model {self.config.model!r} is not installed locally. "
                f"Pull it with 'ollama pull {self.config.model}'."
            )

        return error

    # --- AVAILABILITY ---

    def available(self) -> bool:
        """
        Whether the runtime is reachable and has the configured model.

        Short timeout, and never raises: on a machine where nothing is
        listening this is the common case, not an error, and the panel must
        report it as an unused option rather than hang or go red.
        """
        if not self.config.model:
            return False

        try:
            request = urllib.request.Request(self._url(TAGS_PATH), method="GET")
            with urllib.request.urlopen(request, timeout=AVAILABILITY_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
            logging.debug(f"No local runtime at {self._base()}: {error}")
            return False

        return self.config.model in self._installed_models(payload)

    @staticmethod
    def _installed_models(payload: dict) -> set:
        """
        Model names the runtime reports, with and without their tags.

        A user configures "qwen2.5vl" where the runtime lists
        "qwen2.5vl:latest". Both are the same model and matching only the exact
        string would call a working setup unavailable.
        """
        names = set()

        for entry in payload.get("models") or []:
            name = entry.get("name") or entry.get("model") or ""
            if name:
                names.add(name)
                names.add(name.split(":")[0])

        return names

    # --- URLS ---

    def _base(self) -> str:
        """The configured endpoint, or the conventional one."""
        return (self.config.endpoint or DEFAULT_ENDPOINT).rstrip("/")

    def _url(self, path: str) -> str:
        """A full URL for one of the runtime's paths."""
        return f"{self._base()}{path}"

    def describe(self) -> str:
        """A short line naming this backend, for the panel and the sidecar."""
        return f"local:{self.config.model or 'unconfigured'}"
