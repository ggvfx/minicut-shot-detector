"""
Command Backend — a configured CLI.

The default path, and the one that has to work. A user names an executable and
its arguments; we run it, write the prompt to stdin, and read text from stdout.

Deliberately not an integration with any particular tool. Studios standardise
on agentic CLIs and those change; supporting "run this command" covers every
one of them, including the ones that do not exist yet, and costs us nothing
when they change.

Subprocesses only, exactly as the splitter treats ffmpeg — no vendor SDK, no
Python client library, nothing to pin or to break on upgrade.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List, Optional

from src.backends.adapter import BackendConfig, ModelBackend, ModelReply

# --- PLACEHOLDERS ---

# Substituted into the configured argument list before the command runs, so a
# user can put the image paths wherever their tool expects them.
PROMPT_PLACEHOLDER = "{prompt}"
IMAGES_PLACEHOLDER = "{images}"


class CommandBackend(ModelBackend):
    """
    Runs a user-configured command and reads its stdout.

    Holds no state between calls: one prompt, one process, one reply.
    """

    def __init__(self, config: BackendConfig):
        super().__init__(config)

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        """
        Runs the configured command and returns what it printed.

        Notes:
            The prompt goes on stdin rather than in an argument. A shot
            description with quotes in it would otherwise have to survive
            whatever the platform's shell does to it, which is exactly the
            class of bug that appears only on someone else's machine.

        Raises:
            BackendError: On a non-zero exit, a timeout, or empty output.
                Empty output counts as a failure: a pass that silently
                produced nothing would read downstream as a shot with no
                description, which looks like an unidentifiable shot rather
                than a broken backend.
        """
        # PSEUDOCODE
        # 1. Build the argument list, substituting the image paths.
        # 2. Run it with the prompt on stdin and a timeout from the config.
        # 3. On non-zero exit, raise BackendError with stderr's first lines.
        # 4. Return the stdout text, with the command recorded as the backend.
        raise NotImplementedError

    def available(self) -> bool:
        """Whether the configured executable exists and can be run."""
        # PSEUDOCODE
        # 1. False when no command is configured.
        # 2. Otherwise resolve the executable on PATH and report whether it is
        #    there. Do not run it — availability must be cheap enough for the
        #    environment panel to ask on every refresh.
        raise NotImplementedError
