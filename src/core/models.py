"""
Shared Data Models.

**Used by both tabs.** The structured schemas passed between stages and written
to disk, for the splitter and the identifier alike. Using BaseModel means a
sidecar or a cache can be re-loaded and re-validated later without hand-written
parsing, and a missing field is an error rather than a wrong answer further on.

Grouped by which tab uses them, with the shared source model first. Split this
per-tab only when it grows enough to be worth it, and say why at the time.

Key terms used throughout the project:
- frame     = integer frame index, 0 at the first frame of the source
- boundary  = the frame index on which a new shot STARTS
- shot      = an inclusive frame range, start_frame..end_frame
- timecode  = a display string, derived from frames only at output time
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# =====================================================================
# SHARED
#
# What ffprobe reported about a file. Both tabs read media, so this is the one
# model neither owns.
# =====================================================================

# --- SOURCE ---


class SourceInfo(BaseModel):
    """What ffprobe reported about the source file."""

    path: str
    width: int
    height: int

    # Kept as the exact rational ffmpeg reports (24000/1001), never a rounded
    # float. Rounding the frame rate drifts a frame over a long edit.
    fps_numerator: int = Field(..., description="e.g. 24000")
    fps_denominator: int = Field(..., description="e.g. 1001")

    frame_count: int
    codec: str

    # Carried through to the mezzanine so a 10-bit source is not quietly
    # flattened to 8-bit on the way out.
    pixel_format: str = "yuv420p"

    # Source start timecode, e.g. "10:00:00:00". Sidecar timecodes are offset
    # by this so they match what the editor sees.
    start_timecode: str = "00:00:00:00"

    # True when r_frame_rate and avg_frame_rate disagree — variable frame rate.
    # VFR must be normalised before detection or every boundary drifts.
    is_variable_frame_rate: bool = False

    # Letterbox/pillarbox crop found by cropdetect, as "w:h:x:y".
    detected_crop: Optional[str] = None


# =====================================================================
# THE SPLITTER
#
# Inspecting a mini cut, the boundaries found in it, and what a completed
# split produced.
# =====================================================================

# --- INSPECTION ---


class ProbeReport(BaseModel):
    """
    What inspecting a source told us, and whether a job can proceed.

    The split between `can_split` and `warnings` is deliberate: a variable
    frame rate source cannot be cut accurately at all, while a tight disk is
    the user's call to make.
    """

    source: SourceInfo

    # Duration as a timecode, which reads better than a frame count in the UI.
    duration_timecode: str

    # Where this source's shots should go unless the user says otherwise: a
    # folder of its own beside the source. Worked out here rather than in the
    # browser, because splitting a path correctly on both platforms is exactly
    # the fiddly kind of thing that belongs where it can be tested.
    suggested_output_dir: str

    estimated_gb: float
    free_gb: Optional[float] = None

    can_split: bool = True
    refusal_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class PreparedJob(BaseModel):
    """
    What a source needs before its cuts can be reviewed.

    The mezzanine is the expensive part of a job and has to exist before
    anything can be cut, so it is built first and the review happens against
    it. Cutting afterwards is stream copies, which are quick.
    """

    source: SourceInfo
    mezzanine_path: str
    proxy_path: str

    # What detection found. Each carries the detectors that agreed on it, so
    # review can start with the uncertain ones.
    boundaries: List["Boundary"] = Field(default_factory=list)


# --- DETECTION ---


class Boundary(BaseModel):
    """
    One detected cut: the frame on which a new shot starts.

    A single frame, not a range. Current scope is hard cuts only; dissolves
    would need a start and end and are deliberately deferred.
    """

    frame: int
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # Which detectors found this frame, by name. A list rather than one flag
    # per detector: the set of detectors has already changed once, and the
    # sidecar should record which ones actually agreed rather than implying
    # there will only ever be two.
    found_by: List[str] = Field(default_factory=list)

    @property
    def detectors_agreed(self) -> bool:
        """
        True when more than one pass found this frame independently.

        One detector firing alone is not wrong — it is uncertain, which is what
        gets flagged for a human to glance at.
        """
        return len(self.found_by) > 1


class Shot(BaseModel):
    """
    One shot: an inclusive frame range, plus whatever was written for it.

    `end_frame` is the last frame IN the shot, not the first frame of the next
    one. Off-by-one errors here are the most likely bug in the project, which
    is why every written shot has its frame count asserted and the frames
    either side of every cut hashed against the mezzanine.
    """

    index: int
    start_frame: int
    end_frame: int

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    detectors_agreed: bool = True

    # Where the shot starts and ends in the source's own timecode, stamped by
    # the pipeline from the tested engine. Carried on the shot rather than
    # derived where it is displayed: the front end would otherwise need its own
    # timecode maths, and a second implementation of drop-frame is a second
    # implementation to get wrong.
    start_timecode: Optional[str] = None
    end_timecode: Optional[str] = None

    # Populated once the shot has been cut out of the mezzanine.
    file: Optional[str] = None

    # Set when this shot absorbed a too-short neighbour. Merges are recorded
    # rather than silently applied.
    merge_note: Optional[str] = None

    @property
    def frame_count(self) -> int:
        """Length in frames, inclusive of both ends."""
        return self.end_frame - self.start_frame + 1


# --- VALIDATION & RESULTS ---


class ValidationResult(BaseModel):
    """Outcome of the validation stage. Any failure blocks the job."""

    passed: bool
    checks: Dict[str, bool] = Field(default_factory=dict)
    failures: List[str] = Field(default_factory=list)


class JobResult(BaseModel):
    """
    Everything one splitter run produced. This is what the sidecar serialises.

    `environment` records the resolved ffmpeg build and the version of what
    detected the cuts. When a boundary looks wrong months later, that is how
    you find out what produced it.
    """

    source: SourceInfo
    shots: List[Shot]
    validation: ValidationResult
    environment: Dict[str, str] = Field(default_factory=dict)
    mezzanine_path: Optional[str] = None
    sidecar_path: Optional[str] = None


# =====================================================================
# MODEL BACKENDS
#
# What every backend returns, whatever it is underneath.
# =====================================================================

# --- WHAT A MODEL BACKEND RETURNS ---


class ModelReply(BaseModel):
    """
    What came back, and what produced it.

    The backend and model are recorded alongside the text for the same reason
    the splitter's sidecar records the ffmpeg build: when an answer looks wrong
    weeks later, the first question is what produced it. Unlike the splitter,
    the same input here can give a different answer twice, which makes the
    record more important rather than less.
    """

    text: str
    backend: str
    model: Optional[str] = None
    seconds: float = 0.0


# =====================================================================
# THE IDENTIFIER
#
# The shape of `Observation` is the important one here: it is what the vision
# model is asked for, and deciding it in this file is how the project keeps a
# consistent vocabulary across a batch instead of inheriting whatever a model
# feels like saying.
#
# The schema is a hypothesis until it has been tried on real material.
# =====================================================================

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


# --- WHAT THE PROJECT SUPPLIES ---


class ProjectKnowledge(BaseModel):
    """
    What a production supplies about its own show, plus the film vocabulary.

    Held as text rather than parsed into structure. These files are written by
    people for a model to read, and the moment we impose a schema on them we
    are asking a production to fill in our form instead of describing their
    show. The interpret pass gets them as they are.

    The counts are the exception: the panel says "20 characters, 5 props" so
    someone can see at a glance that the file was read the way they meant it,
    which is the cheapest way to catch a heading typed at the wrong level.

    Attributes:
        production: The show's own markdown — characters, props, environments.
        terminology: Film vocabulary. Ships with the app and is never shown.
        directory: Where the production file was looked for, for the UI.
        counts: Entries found under each category heading.
    """

    production: str = ""
    terminology: str = ""
    directory: Optional[str] = None
    counts: Dict[str, int] = Field(default_factory=dict)

    @property
    def has_production(self) -> bool:
        """Whether the show described itself, or shots stay unnamed."""
        return bool(self.production.strip())

    @property
    def has_terminology(self) -> bool:
        """Always true in practice; here so a caller need not assume it."""
        return bool(self.terminology.strip())


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
