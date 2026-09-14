"""
Tests for the Identifier Pipeline.

The pipeline holds no judgement of its own, so none is tested here. What is
tested is the joining — the same things `test_pipeline.py` tests for the
splitter, and one more that the splitter has no equivalent of.

That one is the cache. The vision pass is the only expensive step in this app,
it costs real money on a metered backend, and every claim made for the
three-pass design rests on it being reused: correcting a character sheet is
only cheap if re-running describes nothing again. A cache that quietly misses
would look exactly like a working app with a larger bill.
"""

import json

import pytest

from src.backends.adapter import BackendError
from src.core.config import IdentifierConfig
from src.core.models import Observation
from src.identifier import pipeline as pipeline_module
from src.identifier.pipeline import CACHE_FILE, FRAMES_DIRECTORY, IdentifierPipeline
from tests.conftest import ScriptedBackend

# --- HELPERS ---

OBSERVED = (
    "subject_count: 1\n"
    "framing: whole body with space above\n"
    "setting: open water\n"
    "appearance: plain untextured blue all over\n"
    "action: the figure stands at the controls of a boat\n"
    "motion: the framing widens\n"
)

INTERPRETED = (
    "shot_size: EWS\n"
    "shot_type: Single\n"
    "characters: Rowan\n"
    "summary: EWS single — Rowan at the controls of a small boat.\n"
)


@pytest.fixture
def shots(tmp_path):
    """A folder of three files that look like shots and one that does not."""
    directory = tmp_path / "shots"
    directory.mkdir()

    for index in range(1, 4):
        (directory / f"cut_{index:03d}.mp4").write_bytes(b"not really video" + bytes([index]))

    (directory / "notes.txt").write_text("ignore me", encoding="utf-8")
    return directory


@pytest.fixture
def wired(monkeypatch):
    """
    Replaces both backends and the frame sampler.

    Sampling is proven against real clips in `test_frames.py`; repeating it here
    would only make these tests slow and dependent on ffmpeg.

    Returns a function taking the two backends and giving back the pipeline.
    """
    def wire(vision: ScriptedBackend, text: ScriptedBackend, **config):
        backends = {"vision": vision, "text": text}

        def backend_for(_pipeline, which):
            return backends[which]

        def one_frame(_sampler, path, into, **_options):
            return [into / f"{path.stem}_001.jpg"]

        monkeypatch.setattr(IdentifierPipeline, "_backend", backend_for)
        monkeypatch.setattr(pipeline_module.FrameSampler, "sample", one_frame)

        return IdentifierPipeline(IdentifierConfig(**config))

    return wire


# --- WHAT STOPS A RUN ---


def test_a_run_with_no_folder_chosen_names_the_missing_setting():
    """Rather than failing later on a path built from None."""
    with pytest.raises(ValueError, match="folder of shots"):
        IdentifierPipeline(IdentifierConfig()).prepare()


def test_a_folder_with_no_video_in_it_says_so(tmp_path, wired):
    """
    An empty table and forty shots nothing could be said about look identical
    in the UI, and only one of them is the user's fault.
    """
    (tmp_path / "readme.txt").write_text("nothing here", encoding="utf-8")
    engine = wired(ScriptedBackend(), ScriptedBackend(), shots_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="No video files"):
        engine.prepare()


def test_a_path_that_is_not_a_folder_is_refused(tmp_path, wired):
    target = tmp_path / "one.mp4"
    target.write_bytes(b"x")
    engine = wired(ScriptedBackend(), ScriptedBackend(), shots_dir=str(target))

    with pytest.raises(RuntimeError, match="Not a folder"):
        engine.prepare()


# --- ONE RUN END TO END ---


def test_every_video_is_described_and_nothing_else_is(shots, wired):
    """The text file in the folder is ignored rather than refused — shot folders have them."""
    vision = ScriptedBackend(OBSERVED)
    engine = wired(vision, ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    records = engine.prepare()

    assert len(records) == 3
    assert vision.calls == 3
    assert all(record.file.endswith(".mp4") for record in records)


def test_the_records_come_back_in_name_order(shots, wired):
    """The table is read against a folder listing, so a shuffled one is unusable."""
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    names = [record.file for record in engine.prepare()]

    assert names == sorted(names)


def test_both_passes_reach_the_record(shots, wired):
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    record = engine.prepare()[0]

    assert record.observation.setting == "open water"
    assert record.interpretation.shot_size == "EWS"
    assert record.interpretation.characters == ["Rowan"]


def test_what_produced_the_answer_is_remembered(shots, wired):
    """
    The same shot can be read differently twice, so which model said it matters
    more here than anywhere in the splitter.
    """
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    record = engine.prepare()[0]

    assert record.backend == "scripted"
    assert record.model == "scripted-1"


def test_only_the_vision_pass_is_given_frames(shots, wired):
    """
    The interpretation pass is text-only by design. Sending it images would
    quietly undo the separation the whole three-pass split exists for, and cost
    a vision call per shot to do it.
    """
    vision, text = ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED)
    wired(vision, text, shots_dir=str(shots)).prepare()

    assert all(frames for frames in vision.images)
    assert not any(text.images)


def test_the_frames_are_written_somewhere_obviously_temporary(shots, wired):
    """
    Not loose among the deliverables. An abandoned run should leave one folder
    a person can delete, rather than three hundred stray JPEGs.
    """
    wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots)).prepare()

    assert (shots / FRAMES_DIRECTORY).is_dir()


# --- WHEN ONE SHOT FAILS ---


def test_a_shot_that_could_not_be_described_does_not_stop_the_others(shots, wired):
    """One unreadable file out of forty is a note on one row, not a failed batch."""
    vision = ScriptedBackend(replies=[OBSERVED, BackendError("the model refused"), OBSERVED])
    engine = wired(vision, ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    records = engine.prepare()

    assert [record.observation is not None for record in records] == [True, False, True]
    assert "the model refused" in records[1].notes
    assert records[2].interpretation is not None, "the batch carried on past the failure"


def test_the_shots_described_before_a_failure_are_kept(shots, wired):
    """
    The cache is written after each shot rather than at the end of the batch.
    A failure on the last shot must not cost the ones already paid for.
    """
    vision = ScriptedBackend(replies=[OBSERVED, OBSERVED, BackendError("out of quota")])
    engine = wired(vision, ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    engine.prepare()
    remembered = json.loads((shots / CACHE_FILE).read_text(encoding="utf-8"))

    assert len(remembered) == 2


def test_an_interpretation_that_failed_leaves_the_observation_alone(shots, wired):
    """
    The expensive half succeeded. Throwing it away because the cheap half
    failed would mean paying for it again to fix a text prompt.
    """
    text = ScriptedBackend(replies=[BackendError("no")] * 3)
    engine = wired(ScriptedBackend(OBSERVED), text, shots_dir=str(shots))

    records = engine.prepare()

    assert all(record.observation for record in records)
    assert all("Could not interpret" in record.notes for record in records)


# --- THE CACHE ---


def test_a_second_run_describes_nothing_again(shots, wired):
    """
    The claim the three-pass design rests on: correct a character sheet, run
    again, and no vision model is touched.
    """
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
    engine.prepare()

    again = ScriptedBackend(OBSERVED)
    wired(again, ScriptedBackend(INTERPRETED), shots_dir=str(shots)).prepare()

    assert again.calls == 0


def test_a_second_run_still_interprets(shots, wired):
    """
    Which is the point of caching only the vision pass. Nothing would be gained
    from re-running if the interpretation were cached too — that is the half
    that changes when the knowledge files do.
    """
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
    engine.prepare()

    text = ScriptedBackend(INTERPRETED)
    records = wired(ScriptedBackend(), text, shots_dir=str(shots)).prepare()

    assert text.calls == 3
    assert all(record.interpretation for record in records)


def test_a_shot_re_exported_under_the_same_name_is_described_again(shots, wired):
    """
    The failure this guards against is silent: a new version of shot 12 gets
    the old shot's description, and every downstream answer is confidently
    about a file nobody is looking at.
    """
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
    engine.prepare()

    (shots / "cut_002.mp4").write_bytes(b"a different export entirely")

    again = ScriptedBackend(OBSERVED)
    wired(again, ScriptedBackend(INTERPRETED), shots_dir=str(shots)).prepare()

    assert again.calls == 1


def test_asking_for_a_fresh_look_overrides_the_cache(shots, wired):
    """For when the prompt changed, or the first answers were plainly wrong."""
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
    engine.prepare()

    again = ScriptedBackend(OBSERVED)
    wired(
        again, ScriptedBackend(INTERPRETED), shots_dir=str(shots), force_observe=True
    ).prepare()

    assert again.calls == 3


def test_an_unreadable_cache_costs_a_re_run_rather_than_the_app(shots, wired):
    """
    It is an optimisation. The worst it may do is describe the batch again;
    refusing to start would leave someone unable to work with no way to fix it.
    """
    (shots / CACHE_FILE).write_text("{ this is not json", encoding="utf-8")
    vision = ScriptedBackend(OBSERVED)

    records = wired(vision, ScriptedBackend(INTERPRETED), shots_dir=str(shots)).prepare()

    assert vision.calls == 3
    assert all(record.observation for record in records)


def test_a_cache_written_by_a_windows_editor_still_reads(shots, wired):
    """Same reason every hand-touchable file in this app is read as utf-8-sig."""
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
    engine.prepare()

    path = shots / CACHE_FILE
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

    again = ScriptedBackend(OBSERVED)
    wired(again, ScriptedBackend(INTERPRETED), shots_dir=str(shots)).prepare()

    assert again.calls == 0


def test_the_cache_survives_the_folder_rather_than_the_session(shots, wired):
    """
    Written beside the shots, so it travels with them and outlives the browser
    tab. The vision pass must never be repeated because someone shut a window.
    """
    wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots)).prepare()

    remembered = json.loads((shots / CACHE_FILE).read_text(encoding="utf-8"))

    assert set(remembered) == {"cut_001.mp4", "cut_002.mp4", "cut_003.mp4"}
    assert Observation.model_validate(remembered["cut_001.mp4"]["observation"]).subject_count == 1


# --- ROWS AS THEY LAND ---


def test_a_shot_is_yielded_before_the_batch_is_finished(shots, wired):
    """
    The point of streaming: row one exists while shots two and three are still
    unread. A table that fills in only at the end cannot be told from a hang.
    """
    engine = wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    stream = engine.prepare_stream()
    first = next(stream)

    assert first.interpretation, "the first row arrived before it was readable"

    rest = list(stream)
    assert len(rest) == 2


def test_streaming_describes_each_shot_exactly_once(shots, wired):
    """Interleaving the two passes must not cost an extra call to either."""
    vision = ScriptedBackend(OBSERVED)
    text = ScriptedBackend(INTERPRETED)
    engine = wired(vision, text, shots_dir=str(shots))

    records = list(engine.prepare_stream())

    assert len(records) == 3
    assert vision.calls == 3
    assert text.calls == 3


def test_streaming_and_blocking_agree(shots, wired):
    """
    `prepare()` is `prepare_stream()` collected, so the two cannot drift. This
    asserts the reading of each shot is the same either way — the interleaving
    changes when the text pass runs, and must not change what it says.
    """
    streamed = list(
        wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
        .prepare_stream()
    )
    blocking = (
        wired(ScriptedBackend(OBSERVED), ScriptedBackend(INTERPRETED), shots_dir=str(shots))
        .prepare()
    )

    assert [record.file for record in streamed] == [record.file for record in blocking]
    assert [record.interpretation for record in streamed] == [
        record.interpretation for record in blocking
    ]


def test_shots_counts_the_batch_without_calling_a_model(shots, wired):
    """The count a progress bar needs must not cost a vision call to learn."""
    vision = ScriptedBackend(OBSERVED)
    engine = wired(vision, ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    listed = engine.shots()

    assert len(listed) == 3
    assert vision.calls == 0


def test_a_failed_shot_is_still_yielded(shots, wired):
    """
    A row that could not be described belongs in the table carrying its note.
    Dropping it would leave a gap the person can neither see nor act on, and
    the streamed run has to behave as the blocking one already does.
    """
    vision = ScriptedBackend(replies=[OBSERVED, BackendError("the model refused"), OBSERVED])
    engine = wired(vision, ScriptedBackend(INTERPRETED), shots_dir=str(shots))

    records = list(engine.prepare_stream())

    assert len(records) == 3, "the failed shot was dropped from the table"
    assert "the model refused" in records[1].notes
    assert records[2].interpretation is not None, "the run carried on past the failure"
