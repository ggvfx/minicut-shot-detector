"""
Identifier Data Models.

The records that pass between the three model passes. Kept here rather than in
`core/models.py` because nothing outside the identifier uses them, and the core
is for what both tabs share.

The shape of `Observation` is the important one: it is what the vision model is
asked for, and deciding it is how the project keeps consistent vocabulary
across a batch instead of inheriting whatever a model feels like saying.

SKELETON. Field names are the agreed shape; the exact observation schema is
expected to change once it has been tried on real material.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# --- WHAT THE VISION PASS REPORTS ---


class Observation(BaseModel):
    """
    What is literally in the picture, in plain words.

    Deliberately free of film terminology. A model asked for "the shot size"
    returns some averaged convention applied inconsistently across forty shots,
    and inconsistent vocabulary is fatal when the next step compares text to
    text. It is asked instead where the frame cuts the subject, and `interpret`
    turns that into the project's own term.

    Equally free of project knowledge: no character names, because a model told
    that a character has blue hair will find blue hair.

    Attributes:
        subject_count: How many people or figures are in frame.
        framing: Where the frame cuts the main subject, in plain words —
            "top of head to shoulders", "full body with headroom".
        foreground: Anything partly blocking the view, which is what an
            over-the-shoulder is before it has a name.
        facing: Which way the main subject faces.
        setting: Where this appears to be.
        appearance: What the figures look like — the evidence a character is
            later identified from, kept so the identification can be checked.
        action: What happens over the sampled frames.
        motion: What changes across them — framing tightening, subject
            crossing frame. Empty for a still reference image.
        raw: The backend's reply as it arrived, so a parse that went wrong can
            be seen rather than guessed at.
    """

    subject_count: Optional[int] = None
    framing: str = ""
    foreground: str = ""
    facing: str = ""
    setting: str = ""
    appearance: List[str] = Field(default_factory=list)
    action: str = ""
    motion: str = ""
    raw: str = ""


# --- WHAT THE FIRST TEXT PASS MAKES OF IT ---


class Interpretation(BaseModel):
    """
    The observation in the project's vocabulary.

    Both halves are kept. `observed` stays visible next to `identified_as` so a
    wrong reading is something a person can see rather than something they have
    to take on trust — the same principle as the frame numbers burned into the
    splitter's review proxy.

    Attributes:
        shot_size: From the terminology file — CS, MS, WS.
        shot_type: OTS, 2-shot, and so on, where the observation supports one.
        characters: Who the appearances were read as.
        evidence: Why — the observed detail behind each identification.
        camera_move: From the terminology file, where there was motion to read.
        location: The setting, in the project's words.
        summary: A one-line description in the project's language, which is
            what the breakdown export shows.
    """

    shot_size: str = ""
    shot_type: str = ""
    characters: List[str] = Field(default_factory=list)
    evidence: Dict[str, str] = Field(default_factory=dict)
    camera_move: str = ""
    location: str = ""
    summary: str = ""


# --- THE SHOT LIST BEING MATCHED AGAINST ---


class ShotListEntry(BaseModel):
    """
    One entry from the production's shot list.

    Comes from a CSV, a text document, or a folder of thumbnails named by shot
    number — a thumbnail is described by the vision pass and interpreted the
    same way, so every source ends as text and there is one matching engine
    rather than two.

    `is_still` matters: a thumbnail cannot show camera movement, so matching
    must not compare an attribute the reference could never have had.
    """

    shot_number: str
    description: str = ""
    interpretation: Optional[Interpretation] = None
    is_still: bool = False


# --- WHAT THE MATCH PASS DECIDES ---


class AttributeMatch(BaseModel):
    """
    Whether one attribute agreed, and what the two sides said.

    Confidence is built from these rather than asked of a model, so each one
    has to carry its own evidence.
    """

    attribute: str
    agreed: bool
    shot_value: str = ""
    entry_value: str = ""


class Candidate(BaseModel):
    """One possible shot number, with the attribute comparison behind it."""

    shot_number: str
    attributes: List[AttributeMatch] = Field(default_factory=list)
    score: float = 0.0


class ShotRecord(BaseModel):
    """
    One video file, everything learned about it, and what it was matched to.

    This is the row in the table, and what gets cached beside the files so the
    vision pass is never repeated.

    `shot_number` stays None when nothing matched well enough. An unnamed shot
    is a correct answer — guessing produces a wrongly named file, which is
    worse than an obviously unnamed one and much harder to notice.
    """

    file: str
    observation: Optional[Observation] = None
    interpretation: Optional[Interpretation] = None

    shot_number: Optional[str] = None
    confidence: float = 0.0
    notes: str = ""
    candidates: List[Candidate] = Field(default_factory=list)

    approved: bool = False
    renamed_to: Optional[str] = None

    # What produced the observation, so an answer that looks wrong months later
    # can be traced. The same input can give a different answer twice here,
    # which makes the record matter more than it does in the splitter.
    backend: str = ""
    model: str = ""
