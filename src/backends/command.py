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
"""

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from src.backends.adapter import BackendConfig, BackendError, ModelBackend, ModelReply

# --- PLACEHOLDERS ---

# Substituted into the configured argument list before the command runs, so a
# user can put the values wherever their tool expects them.
#
# {images} expands to one argument per frame rather than to a joined string:
# a tool taking `--image a.jpg --image b.jpg` and one taking `a.jpg b.jpg` are
# both expressible, and neither needs the user to think about quoting.
PROMPT_PLACEHOLDER = "{prompt}"
IMAGE_PLACEHOLDER = "{image}"
IMAGES_PLACEHOLDER = "{images}"

# How much of stderr to quote when a command fails. Enough to carry the real
# message, not so much that a stack trace fills the panel.
STDERR_LINES = 4


class CommandBackend(ModelBackend):
    """
    Runs a user-configured command and reads its stdout.

    Holds no state between calls: one prompt, one process, one reply.
    """

    def __init__(self, config: BackendConfig):
        super().__init__(config)

    # --- SENDING ---

    def send(self, prompt: str, images: Optional[List[Path]] = None) -> ModelReply:
        """
        Runs the configured command and returns what it printed.

        Notes:
            The prompt goes on stdin unless the argument list asks for it by
            name. A shot description with quotes or newlines in it would
            otherwise have to survive whatever the platform's shell does to it,
            which is exactly the class of bug that appears only on someone
            else's machine.

        Raises:
            BackendError: On a missing executable, a non-zero exit, a timeout,
                or empty output.
        """
        if not self.config.command:
            raise BackendError("No command is configured for this backend")

        if images and not self._takes_images():
            raise BackendError(
                f"{self.config.command[0]} was given {len(images)} frames but the "
                f"command has nowhere to put them. Add {IMAGES_PLACEHOLDER} or "
                f"{IMAGE_PLACEHOLDER} to its arguments, or set an image "
                f"reference for tools that read paths from the prompt."
            )

        prompt = self._with_references(prompt, images or [])
        args = self._build_args(prompt, images or [])
        on_stdin = PROMPT_PLACEHOLDER not in self.config.command

        logging.debug(f"Running backend command: {args[0]} ({len(args) - 1} arguments)")
        started = time.monotonic()

        try:
            result = subprocess.run(
                args,
                input=prompt if on_stdin else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as error:
            raise BackendError(
                f"The command {args[0]!r} was not found. "
                f"Check the path, or that it is installed on this machine."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise BackendError(
                f"{args[0]} did not answer within {self.config.timeout_seconds}s. "
                f"Raise the timeout, or use fewer frames per shot."
            ) from error
        except OSError as error:
            raise BackendError(f"Could not run {args[0]!r}: {error}") from error

        if result.returncode != 0:
            raise BackendError(
                f"{args[0]} exited with code {result.returncode}: {self._tail(result.stderr)}"
            )

        text = (result.stdout or "").strip()
        if not text:
            raise BackendError(
                f"{args[0]} exited cleanly but printed nothing. {self._tail(result.stderr)}"
            )

        return ModelReply(
            text=text,
            backend=f"command:{Path(args[0]).name}",
            model=self.config.model,
            seconds=round(time.monotonic() - started, 2),
        )

    def _with_references(self, prompt: str, images: List[Path]) -> str:
        """
        Adds image references to the prompt, for tools that want them there.

        Claude Code reads `@path`; others take arguments instead. Appended
        after the instruction rather than before, so the reference sits next to
        the question it answers and the prompt still reads as a prompt.
        """
        if not images or not self.config.image_reference:
            return prompt

        references = "\n".join(
            self.config.image_reference.format(path=path) for path in images
        )

        return f"{prompt}\n\n{references}"

    def _takes_images(self) -> bool:
        """
        Whether the configured command has anywhere to put a frame.

        Checked before sending rather than after, because silently dropping the
        images is the worst failure available here: the model answers from the
        prompt alone, the reply looks exactly like an observation, and every
        field in it is invented. Better to refuse and say which placeholder is
        missing.
        """
        if self.config.image_reference:
            return True

        return any(
            item == IMAGES_PLACEHOLDER or IMAGE_PLACEHOLDER in item
            for item in self.config.command or []
        )

    def _build_args(self, prompt: str, images: List[Path]) -> List[str]:
        """
        Substitutes the placeholders into the configured argument list.

        Notes:
            {images} expands in place to one argument per frame, so an empty
            frame list leaves no stray empty argument behind — some tools treat
            one of those as a filename and fail confusingly.
        """
        args: List[str] = []

        for item in self.config.command or []:
            if item == IMAGES_PLACEHOLDER:
                args.extend(str(path) for path in images)
            elif IMAGE_PLACEHOLDER in item:
                # Repeated per frame, so `--image={image}` becomes one flag each
                args.extend(item.replace(IMAGE_PLACEHOLDER, str(path)) for path in images)
            elif item == PROMPT_PLACEHOLDER:
                args.append(prompt)
            else:
                args.append(item)

        return args

    @staticmethod
    def _tail(stderr: Optional[str]) -> str:
        """The last few lines of stderr, for an error message."""
        if not stderr or not stderr.strip():
            return "It wrote nothing to stderr."

        lines = [line for line in stderr.strip().splitlines() if line.strip()]
        return " / ".join(lines[-STDERR_LINES:])

    # --- AVAILABILITY ---

    def available(self) -> bool:
        """
        Whether the configured executable exists and could be run.

        Resolves it on PATH without running it: the environment panel asks on
        every refresh, and a panel that invokes a model to find out whether a
        model is there would be both slow and, on a metered API, expensive.
        """
        if not self.config.command:
            return False

        executable = self.config.command[0]

        # An absolute or relative path is checked directly; a bare name is
        # looked up on PATH, which is how a user would have typed it
        if Path(executable).is_file():
            return True

        return shutil.which(executable) is not None

    def describe(self) -> str:
        """A short line naming this backend, for the panel and the sidecar."""
        if not self.config.command:
            return "command:unconfigured"
        return f"command:{Path(self.config.command[0]).name}"
