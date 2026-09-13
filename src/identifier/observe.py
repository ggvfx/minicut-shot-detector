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
told that a character has blue hair will find blue hair. Naming happens
afterwards, from what was actually reported, with the evidence kept so a wrong
reading is visible.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from src.backends.adapter import BackendError, ModelBackend
from src.core.models import Observation

# --- THE SCHEMA ---

# What the model is asked for. Each is something a person could point at in the
# picture, which is what keeps answers comparable between shots and between
# models.
#
# Each is phrased as a question rather than a field name, because a bare label
# is not something a model answers the same way twice: "framing" invites an
# essay, "where does the frame cut the main figure?" invites an answer.
#
# Expected to change once it has been tried on real material — the fields are a
# hypothesis, not a settled contract.
OBSERVATION_FIELDS = {
    "subject_count": "How many people or figures are in frame? Answer with a number.",
    "framing": (
        "Where does the frame cut the main figure? Say it plainly, for example "
        "'top of head to shoulders', 'waist up', 'whole body with space above'. "
        "If no figure is in frame, say 'no figure'."
    ),
    "foreground": (
        "Is anything close to the camera partly blocking the view? Say what it is "
        "and which side, or 'nothing'."
    ),
    "facing": "Which way is the main figure facing — towards camera, away, or in profile?",
    "setting": "Where does this appear to be? One short phrase.",
    "appearance": (
        "Describe each figure in a few words — colour, clothing, hair, anything "
        "carried or worn. If a figure is a plain untextured colour, say which "
        "colour. One figure per line."
    ),
    "action": "What is happening? One short sentence.",
    "motion": (
        "Compare the frames in order. Does the framing tighten, widen, or stay the "
        "same? Does anything move across the frame? Answer 'static' if nothing "
        "changes."
    ),
}

# Fields whose answer is a list rather than a phrase.
LIST_FIELDS = ("appearance",)

# Dropped for a still reference image, where there is no motion to report and
# asking for it invites invention.
MOTION_FIELD = "motion"

# What the model is asked to say when no image arrived, so a misconfigured
# backend fails loudly instead of returning a description of nothing.
NO_IMAGE_REPLY = "NO IMAGE"


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
            ValueError: If no frames were given. An observation of nothing is
                not something to ask a model for.
            BackendError: Passed through from the backend. A failed shot is
                reported as failed rather than left blank — an empty
                description reads downstream as an unidentifiable shot, which
                hides the real problem.
        """
        if not frames:
            raise ValueError("No frames to observe")

        reply = self.backend.send(build_prompt(len(frames), is_still), images=frames)
        return parse_reply(reply.text, is_still)


# --- THE PROMPT ---


def build_prompt(frame_count: int, is_still: bool = False) -> str:
    """
    The instruction sent with the frames.

    Notes:
        Two refusals do the work here, and both are deliberate.

        It is told **not** to use film terminology, because an averaged
        convention applied inconsistently across a batch is fatal when the next
        step compares text to text.

        It is told **nothing about the production** — no character names, no
        story. A model told a character has blue hair will find blue hair.

        And it is given a way to say the image never arrived. Found by testing:
        the first real run reached a model with no image attached, and only
        because that model pushed back did it not return seven invented
        fields. A backend misconfiguration must not look like a description.
    """
    fields = {
        name: question
        for name, question in OBSERVATION_FIELDS.items()
        if not (is_still and name == MOTION_FIELD)
    }

    opening = (
        "You are looking at one still image."
        if is_still
        else (
            f"You are looking at {frame_count} frames taken in order from a single shot "
            f"of video. They are the same shot at different moments, not different shots."
        )
    )

    questions = "\n".join(f"{name}: {question}" for name, question in fields.items())

    return "\n".join([
        opening,
        "",
        "Answer each question below about what you can actually see. Use plain",
        "description only.",
        "",
        'Do NOT use film or camera terminology — no "close-up", "wide", "over the',
        'shoulder", "dolly", "pan". Describe what is in the picture and where the',
        "frame cuts, and let someone else name it.",
        "",
        "Do not guess at names, story or intent. If something is not visible, say",
        "so rather than inventing it.",
        "",
        "If no image reached you, reply with exactly: NO IMAGE",
        "Do not describe anything in that case.",
        "",
        "Reply with one line per field, in this exact form:",
        "",
        "field: your answer",
        "",
        questions,
    ])


# --- READING THE REPLY ---


def parse_reply(reply: str, is_still: bool = False) -> Observation:
    """
    Reads the model's reply into the schema.

    Notes:
        Tolerant by design. Models wrap answers in prose, in code fences, or
        answer in a different order, and a batch of forty must not fail because
        one reply had a preamble. Anything unreadable leaves that field empty
        and keeps the raw text — an empty field is honest, and the raw reply is
        what makes it debuggable.
    """
    text = re.sub(r"^```[a-z]*\n?|```$", "", reply.strip(), flags=re.MULTILINE)

    # A backend misconfiguration must not look like a description. The first
    # real run of this reached a model with no image attached, and only because
    # that model pushed back did it not return seven invented fields.
    if NO_IMAGE_REPLY in text.upper()[:200]:
        raise BackendError(
            "The model reported that no image reached it. Check that the frames "
            "are actually being passed to the backend."
        )

    observation = Observation(raw=reply)
    found = 0

    for name in OBSERVATION_FIELDS:
        value = _field(text, name)
        if not value:
            continue

        found += 1

        if name in LIST_FIELDS:
            setattr(observation, name, _as_lines(value))
        elif name == "subject_count":
            observation.subject_count = _as_count(value)
        else:
            setattr(observation, name, value)

    if not found:
        logging.warning("No fields could be read from the reply; keeping it raw")

    if is_still:
        observation.motion = ""

    return observation


def _field(text: str, name: str) -> str:
    """
    One field's answer: everything after its label, up to the next label.

    Notes:
        Bounded by the other field names rather than by the end of the line,
        because a model will happily answer `appearance` over four lines and
        then start the next field — and taking only the first line would throw
        away three quarters of the useful answer.
    """
    others = "|".join(other for other in OBSERVATION_FIELDS if other != name)
    match = re.search(
        rf"^\W*{name}\W*:\s*(.*?)(?=^\W*(?:{others})\W*:|\Z)",
        text,
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )

    return match.group(1).strip() if match else ""


def _as_lines(value: str) -> List[str]:
    """One entry per line, with list bullets and numbering stripped."""
    lines = [re.sub(r"^[-*\d.)\s]+", "", line).strip() for line in value.splitlines()]
    return [line for line in lines if line]


def _as_count(value: str) -> Optional[int]:
    """
    The first whole number in an answer.

    Models answer "2", "two people" or "2 (both standing)" to the same
    question, and taking the first number handles all three. A reply with no
    number leaves the field unset rather than guessing at zero, because "none
    visible" and "could not tell" are different answers.
    """
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None
