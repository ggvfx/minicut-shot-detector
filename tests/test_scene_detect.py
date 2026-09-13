"""
Tests for the PySceneDetect Passes.

Run against a generated clip whose cuts are known exactly, because a detector
tested on footage nobody has labelled can only be checked for plausibility.
"""

import subprocess

import pytest

from src.splitter.scene_detect import (
    ADAPTIVE,
    CONTENT,
    SceneDetectPass,
    detect_all,
)

# --- FIXTURE ---

# Three seconds at 24fps, cutting from colour to colour every second. The cuts
# are therefore at exactly frames 24 and 48 — the strongest possible signal,
# which is what makes a miss here meaningful rather than debatable.
CUT_FRAMES = (24, 48)


@pytest.fixture(scope="module")
def cut_clip(ffmpeg_available, tmp_path_factory):
    """A clip with two unmistakable hard cuts in it."""
    if not ffmpeg_available:
        pytest.skip("ffmpeg is not installed")

    output = tmp_path_factory.mktemp("cuts") / "three_shots.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:size=320x240:rate=24:duration=1",
            "-f", "lavfi", "-i", "color=c=green:size=320x240:rate=24:duration=1",
            "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=24:duration=1",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[out]",
            "-map", "[out]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    return output


def near(boundaries, frame, tolerance=2):
    """Whether any boundary landed within a couple of frames of one we expect."""
    return any(abs(boundary.frame - frame) <= tolerance for boundary in boundaries)


# --- DETECTION ---


@pytest.mark.parametrize("kind", [CONTENT, ADAPTIVE])
def test_a_detector_finds_unmistakable_cuts(cut_clip, kind):
    """Red to green to blue is as clear as a cut gets: both must find both."""
    boundaries = SceneDetectPass(kind).detect(cut_clip)

    for frame in CUT_FRAMES:
        assert near(boundaries, frame), f"{kind} missed the cut at frame {frame}"


@pytest.mark.parametrize("kind", [CONTENT, ADAPTIVE])
def test_boundaries_record_which_detector_found_them(cut_clip, kind):
    """The sidecar reports agreement, so every boundary must name its source."""
    boundaries = SceneDetectPass(kind).detect(cut_clip)

    assert boundaries
    assert all(boundary.found_by == [kind] for boundary in boundaries)


def test_the_first_scene_is_not_a_boundary(cut_clip):
    """
    PySceneDetect counts the opening scene, which starts at frame 0.

    Frame 0 is where the first shot begins, not a cut, and passing it on would
    open a shot with no frames in it.
    """
    boundaries = SceneDetectPass(CONTENT).detect(cut_clip)

    assert all(boundary.frame > 0 for boundary in boundaries)


def test_frames_are_plain_integers(cut_clip):
    """
    PySceneDetect works in its own FrameTimecode type.

    It converts at this boundary and never leaks further — everything
    downstream does integer arithmetic on frame numbers.
    """
    boundaries = SceneDetectPass(CONTENT).detect(cut_clip)

    assert all(isinstance(boundary.frame, int) for boundary in boundaries)


def test_detect_all_returns_one_list_per_detector(cut_clip):
    """
    Kept separate rather than combined, so the merge can tell who found what.
    """
    passes = detect_all(cut_clip)

    assert len(passes) == 2
    assert {boundary.found_by[0] for pass_ in passes for boundary in pass_} == {CONTENT, ADAPTIVE}


def test_an_unknown_detector_is_refused():
    with pytest.raises(ValueError, match="Unknown detector"):
        SceneDetectPass("magic")
