"""
Core Data Models for the Shot Splitter.

Defines the structured schemas passed between pipeline stages and written to
the JSON sidecar. Using BaseModel means the sidecar can be re-loaded and
re-validated later without hand-written parsing.

Key terms used throughout the project:
- frame     = integer frame index, 0 at the first frame of the source
- boundary  = the frame index on which a new shot STARTS
- shot      = an inclusive frame range, start_frame..end_frame
- timecode  = a display string, derived from frames only at output time
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

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

    # Source start timecode, e.g. "10:00:00:00". Sidecar timecodes are offset
    # by this so they match what the editor sees.
    start_timecode: str = "00:00:00:00"

    # True when r_frame_rate and avg_frame_rate disagree — variable frame rate.
    # VFR must be normalised before detection or every boundary drifts.
    is_variable_frame_rate: bool = False

    # Letterbox/pillarbox crop found by cropdetect, as "w:h:x:y".
    detected_crop: Optional[str] = None


class ProbeReport(BaseModel):
    """
    What inspecting a source told us, and whether a job can proceed.

    The split between `can_split` and `warnings` is deliberate: a variable
    frame rate source cannot be cut accurately at all, while a tight disk is
    the user's call to make.
    """

    source: SourceInfo
    detected_crop: Optional[str] = None

    # Duration as a timecode, which reads better than a frame count in the UI.
    duration_timecode: str

    estimated_gb: float
    free_gb: Optional[float] = None

    can_split: bool = True
    refusal_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


# --- DETECTION ---


class Boundary(BaseModel):
    """
    One detected cut: the frame on which a new shot starts.

    A single frame, not a range. Current scope is hard cuts only; dissolves
    would need a start and end and are deliberately deferred.
    """

    frame: int
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # Which detectors fired here. Both agreeing is the confident case; one
    # firing alone is what gets flagged for human review.
    found_by_transnet: bool = False
    found_by_scenedetect: bool = False

    @property
    def detectors_agreed(self) -> bool:
        """True when both passes independently found this boundary."""
        return self.found_by_transnet and self.found_by_scenedetect


class Shot(BaseModel):
    """
    One shot: an inclusive frame range, plus whatever was written for it.

    `end_frame` is the last frame IN the shot, not the first frame of the next
    one. Off-by-one errors here are the most likely bug in the project, which
    is exactly what the golden set is there to catch.
    """

    index: int
    start_frame: int
    end_frame: int

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    detectors_agreed: bool = True

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

    `environment` records the resolved ffmpeg build, onnxruntime version and
    model checksum. When a boundary looks wrong months later, that is how you
    find out what produced it.
    """

    source: SourceInfo
    shots: List[Shot]
    validation: ValidationResult
    environment: Dict[str, str] = Field(default_factory=dict)
    mezzanine_path: Optional[str] = None
    sidecar_path: Optional[str] = None
