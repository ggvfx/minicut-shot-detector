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

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from src.backends.adapter import BackendConfig, ModelBackend, ModelReply

# --- DEFAULTS ---

# Where local runtimes conventionally listen. Configurable, because someone
# will run it on another machine on their own network.
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"


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
        # PSEUDOCODE
        # 1. Post prompt and any images to the runtime's generate endpoint.
        # 2. A connection refusal means the runtime is not running: say so,
        #    and say how to start it.
        # 3. A missing model means it has not been pulled: name it and give
        #    the pull command.
        # 4. Return the text, recording the model.
        raise NotImplementedError

    def available(self) -> bool:
        """Whether the runtime is reachable and has the configured model."""
        # PSEUDOCODE
        # 1. Ask the runtime for its model list, with a short timeout — the
        #    panel must not hang on a machine where nothing is listening.
        # 2. True when it answers and the configured model is among them.
        raise NotImplementedError
