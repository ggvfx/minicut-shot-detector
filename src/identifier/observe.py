"""
Pass 1 — Observation.

The only pass that sees images, and the only one that needs a vision model. It
runs once per shot and its result is cached, which is what makes every later
correction cheap.

Two rules define it, and both are about what it is *not* asked:

**No film terminology.** A model asked for "the shot size" answers with some
averaged convention, applied differently on shot 3 and shot 30. Inconsistent
vocabulary is fatal when the next step compares text to text. It is asked where
the frame cuts the subject; `interpret` turns that into the project's term.

**No project knowledge.** The character sheet is not in this prompt. A model
told that Tess has blue hair and rollerskates will find blue hair and
rollerskates. Naming happens afterwards, from what was actually reported, with
the evidence kept so a wrong reading is visible.

SKELETON. Signatures and docstrings only.
"""

from pathlib import Path
from typing import List

from src.backends.adapter import ModelBackend
from src.core.models import Observation

# --- THE SCHEMA ---

# What the model is asked for. Each is something a person could point at in the
# picture, which is what keeps answers comparable between shots and between
# models. Expected to change once it has been tried on real material — the
# fields are a hypothesis, not a settled contract.
OBSERVATION_FIELDS = (
    "subject_count",
    "framing",
    "foreground",
    "facing",
    "setting",
    "appearance",
    "action",
    "motion",
)


class Observer:
    """
    Turns frames into a plain description of what is in them.

    Holds the backend and the prompt. One call per shot, however many frames.
    """

    def __init__(self, backend: ModelBackend):
        self.backend = backend

    def observe(self, frames: List[Path], is_still: bool = False) -> Observation:
        """
        Describes what the frames show.

        Args:
            frames: Sample frames in time order. Their order is the only motion
                information available, so it is stated in the prompt.
            is_still: True for a reference thumbnail, where there is no motion
                to report and asking for it invites invention.

        Returns:
            Observation: the parsed fields, with the reply kept in `raw`.

        Raises:
            BackendError: Passed through from the backend. A failed shot is
                reported as failed rather than left blank — an empty
                description reads downstream as an unidentifiable shot, which
                hides the real problem.
        """
        # PSEUDOCODE
        # 1. Build the prompt: the schema, one field per line, asking for plain
        #    words and explicitly not for film terms.
        # 2. Say how many frames there are and that they are in time order.
        # 3. For a still, drop the motion field from the schema entirely.
        # 4. Send prompt and frames.
        # 5. Parse the reply into Observation, keeping the raw text.
        raise NotImplementedError

    @staticmethod
    def _parse(reply: str) -> Observation:
        """
        Reads the model's reply into the schema.

        Notes:
            Tolerant by design. Models wrap answers in prose, in code fences,
            or answer in a different order, and a batch of forty must not fail
            because one reply had a preamble. Anything unreadable leaves that
            field empty and keeps the raw text — an empty field is honest, and
            the raw reply is what makes it debuggable.
        """
        # PSEUDOCODE
        # 1. Strip code fences and any preamble.
        # 2. Take field: value lines, matching names case-insensitively.
        # 3. Leave anything missing or unparseable empty.
        # 4. Return the Observation with `raw` set to the whole reply.
        raise NotImplementedError
