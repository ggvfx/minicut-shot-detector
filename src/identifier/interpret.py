"""
Pass 2 — Interpretation.

Turns a plain observation into the project's own vocabulary, using the markdown
files the user supplies. Text in, text out: no images, no vision model.

This is where "top of head to shoulders" becomes CS, and where a red mannequin
on rollerskates becomes "likely Tess" — and it is a separate pass precisely so
that neither piece of knowledge was in the room when the picture was described.

Being text-only is what makes it cheap to re-run. Correct the terminology file,
add a character who was missed, and forty shots are re-interpreted from cached
observations in seconds, with no vision model and no per-image cost.

SKELETON. Signatures and docstrings only.
"""

from src.backends.adapter import ModelBackend
from src.core.models import Interpretation, Observation, ProjectKnowledge


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
            is what lets a person see that "Tess" was decided from "red
            mannequin, rollerskates" and disagree with it.

        Notes:
            Identification is allowed to decline. An appearance that matches no
            character is left unnamed and the description kept, because a
            confidently wrong name is harder to spot than a missing one.

            With no knowledge files loaded this still produces a summary, in
            plain words. That is the reduced-but-useful case the breakdown
            export relies on for a show with no character sheet.
        """
        # PSEUDOCODE
        # 1. Build the prompt: the observation, then the terminology file, then
        #    the character file, each clearly labelled.
        # 2. Ask for the project's term for framing and camera move, using only
        #    the terminology given — not the model's own conventions.
        # 3. Ask which characters the appearances match, with the observed
        #    detail behind each, and to name nobody where nothing matches.
        # 4. Ask for a one-line summary in the project's language.
        # 5. Parse into Interpretation, leaving unreadable fields empty.
        raise NotImplementedError
