"""
HTTP API Backend.

For people with a key and no wish to run anything locally. Plain HTTP against a
configured endpoint — no vendor SDK, for the same reason the splitter shells
out to ffmpeg rather than importing a binding: one fewer dependency to pin, and
nothing that breaks when a library reorganises itself.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from src.backends.adapter import BackendConfig, ModelBackend, ModelReply


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

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        """
        Posts the prompt and any images, and returns the text.

        Raises:
            BackendError: On a transport failure, a non-success status, or a
                body that does not contain text where expected. The message
                says which of those happened and never quotes the key.
        """
        # PSEUDOCODE
        # 1. Read the key from the named environment variable; if absent,
        #    raise BackendError naming the variable rather than the key.
        # 2. Base64 the images, if any.
        # 3. Post prompt and images to the endpoint, with the config's timeout.
        # 4. On a rate limit, raise rather than retry silently: a forty shot
        #    batch must not turn into a slow accidental retry storm.
        # 5. Return the text, recording endpoint and model.
        raise NotImplementedError

    def available(self) -> bool:
        """Whether an endpoint is configured and its key is in the environment."""
        # PSEUDOCODE
        # 1. False when no endpoint is configured.
        # 2. True when the named environment variable is set and not empty.
        #    Do not call the endpoint — availability must not cost money.
        raise NotImplementedError
