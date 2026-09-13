"""
Pass 2 — Interpretation.

Turns a plain observation into the project's own vocabulary. Text in, text out:
no images, no vision model.

This is where "top of head to shoulders" becomes CS, and where a plain red
mannequin becomes "likely Vega" — and it is a separate pass precisely so that
neither piece of knowledge was in the room when the picture was described.

Being text-only is what makes it cheap to re-run. Correct the terminology, add
a character who was missed, and forty shots are re-interpreted from cached
observations in seconds, with no vision model and no per-image cost.
"""

import logging
import re
from typing import Dict, List

from src.backends.adapter import ModelBackend
from src.core.models import Interpretation, Observation, ProjectKnowledge
from src.identifier.replies import field_value, strip_bullet, unfence

# --- WHAT IS ASKED FOR ---

# Named the same way the observation fields are, and for the same reason: a
# label is not a question. Each says what a good answer looks like.
INTERPRETATION_FIELDS = {
    "shot_size": (
        "Using ONLY the terminology given, which shot size is this? Answer with "
        "the term alone, or 'unclear' if the observation does not say enough."
    ),
    "shot_type": (
        "Using ONLY the terminology given, which shot type is this — how many "
        "subjects, over-the-shoulder, point of view, insert? The term alone, or "
        "'unclear'."
    ),
    "camera_move": (
        "Using ONLY the terminology given, which camera move is this? The term "
        "alone, or 'unclear'. Answer 'static' only if the observation says "
        "nothing changes."
    ),
    "characters": (
        "Which named characters from the production notes do the observed "
        "figures match? Comma separated, in the order they were observed. Write "
        "'unknown' for any figure matching nobody, and 'none' if there are no "
        "figures at all."
    ),
    "evidence": (
        "For each character you named, the observed detail that identified them, "
        "as 'Name: detail'. One per line. Nothing for figures you left unknown."
    ),
    "location": (
        "Which named environment from the production notes is this, or a short "
        "plain phrase if it matches none."
    ),
    "summary": (
        "One sentence describing this shot, in the project's own terms, as it "
        "would appear on a shot list. Lead with the shot size and type."
    ),
}

LIST_FIELDS = ("characters",)
MAP_FIELDS = ("evidence",)

# Answers that mean "I could not tell", normalised away so an empty field and a
# model politely saying nothing look the same downstream.
NON_ANSWERS = {"unclear", "unknown", "none", "n/a", "not visible", "not stated", ""}


class Interpreter:
    """
    Applies project knowledge to an observation.

    Holds the backend and the knowledge, since both are the same for every shot
    in a batch.
    """

    def __init__(self, backend: ModelBackend, knowledge: ProjectKnowledge):
        self.backend = backend
        self.knowledge = knowledge

    def interpret(self, observation: Observation) -> Interpretation:
        """
        Reads an observation in the project's terms.

        Returns:
            Interpretation: terms and character names, each kept alongside the
            observed detail it came from. The evidence is not decoration — it
            is what lets a person see that "Vega" was decided from "plain red
            figure" and disagree with it.

        Notes:
            Identification is allowed to decline. An appearance matching no
            character is left unnamed and the description kept, because a
            confidently wrong name is harder to spot than a missing one.

            With no knowledge loaded this still produces a summary, in plain
            words. That is the reduced-but-useful case the breakdown export
            relies on for a show with no character list yet.
        """
        reply = self.backend.send(self.build_prompt(observation))
        return parse_reply(reply.text)

    # --- THE PROMPT ---

    def build_prompt(self, observation: Observation) -> str:
        """
        The observation, then the knowledge, then the questions.

        Notes:
            The observation comes first and is fenced off as a quotation. It is
            the evidence; the knowledge is the dictionary. Putting the
            dictionary first invites the model to go looking for its contents
            in the picture, which is the failure this whole two-pass split
            exists to prevent — and it would be invisible, because a shot
            confidently labelled with the wrong character still reads like a
            result.
        """
        parts = [
            "You are turning a plain description of one shot into a production's",
            "own vocabulary. You cannot see the shot. Work only from the",
            "description below — do not add anything it does not support.",
            "",
            "=== WHAT WAS OBSERVED ===",
            _describe(observation),
            "",
        ]

        if self.knowledge.has_terminology:
            parts += ["=== SHOT TERMINOLOGY ===", self.knowledge.terminology.strip(), ""]

        if self.knowledge.has_production:
            parts += ["=== PRODUCTION NOTES ===", self.knowledge.production.strip(), ""]

        parts += [
            "=== ANSWER THESE ===",
            "",
            "One line per field, in this exact form:",
            "",
            "field: your answer",
            "",
            "Use only terms from the terminology above. If the observation does not",
            "support an answer, say 'unclear' rather than guessing — an unnamed",
            "shot is a correct answer and a wrongly named one is not.",
            "",
        ]
        parts += [f"{name}: {question}" for name, question in INTERPRETATION_FIELDS.items()]

        return "\n".join(parts)


def _describe(observation: Observation) -> str:
    """
    The observation as the lines it was reported in.

    Sent as text rather than as the raw reply: the raw may carry a preamble, a
    code fence or an apology, and none of that is evidence about the picture.
    """
    lines = []

    if observation.subject_count is not None:
        lines.append(f"figures in frame: {observation.subject_count}")

    for name in ("framing", "foreground", "facing", "setting", "action", "motion"):
        value = getattr(observation, name)
        if value:
            lines.append(f"{name}: {value}")

    for index, appearance in enumerate(observation.appearance, start=1):
        lines.append(f"figure {index}: {appearance}")

    return "\n".join(lines) if lines else "(nothing was reported)"


# --- READING THE REPLY ---


def parse_reply(reply: str) -> Interpretation:
    """
    Reads the model's reply into the schema.

    Tolerant in the same way the observation parser is, and for the same
    reason: a batch of forty must not fail because one reply had a preface.
    """
    text = unfence(reply)
    interpretation = Interpretation()

    for name in INTERPRETATION_FIELDS:
        value = field_value(text, name, _others(name))
        if not value:
            continue

        if name in LIST_FIELDS:
            interpretation.characters = _as_names(value)
        elif name in MAP_FIELDS:
            interpretation.evidence = _as_map(value)
        elif _is_answer(value):
            setattr(interpretation, name, value.strip())

    return interpretation


def _others(name: str) -> List[str]:
    """Every field but this one — what bounds its answer."""
    return [other for other in INTERPRETATION_FIELDS if other != name]


def _is_answer(value: str) -> bool:
    """Whether a field actually said something."""
    return value.strip().lower().rstrip(".") not in NON_ANSWERS


def _as_names(value: str) -> List[str]:
    """
    Character names, with the declines dropped.

    Notes:
        "unknown" is not carried through as a name. A figure nobody could
        place is an absence, and keeping the word would put it in the text the
        matcher compares — where it would match every other unplaceable figure
        in the batch.
    """
    names = [part.strip(" .") for part in re.split(r"[,\n]", value)]
    return [name for name in names if name and _is_answer(name)]


def _as_map(value: str) -> Dict[str, str]:
    """`Name: detail` per line, for showing beside each identification."""
    evidence = {}

    for line in value.splitlines():
        line = strip_bullet(line)
        if ":" not in line:
            continue

        name, _, detail = line.partition(":")
        name, detail = name.strip(), detail.strip()

        if name and detail and _is_answer(name):
            evidence[name] = detail

    if not evidence and value.strip():
        logging.debug("Evidence was given but not in 'Name: detail' form")

    return evidence
