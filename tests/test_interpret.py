"""
Tests for the Interpretation Pass.

Two things are worth testing here, and neither is the model's judgement.

The first is the prompt's shape. The observation has to arrive before the
production notes, because the whole two-pass split exists to stop a model
going looking for a character it has just been told about — and that failure
is invisible from the outside, since a shot confidently labelled with the wrong
name reads exactly like a result.

The second is the parser. It runs forty times a batch on text a model wrote
freehand, and every tolerance in it is here because something real came back in
that shape.
"""

from src.core.models import Interpretation, Observation, ProjectKnowledge
from src.identifier.interpret import INTERPRETATION_FIELDS, Interpreter, parse_reply
from tests.conftest import ScriptedBackend

# --- HELPERS ---


def an_observation(**fields) -> Observation:
    """An observation with enough in it to interpret, overridable per test."""
    return Observation(**{
        "subject_count": 1,
        "framing": "whole body with space above and below",
        "setting": "open water",
        "appearance": ["plain untextured blue all over, no face"],
        "action": "the figure stands at the controls of a small boat",
        "motion": "the framing widens and lifts",
        **fields,
    })


PRODUCTION = "# Characters\n\n## Rowan\n\n**Blocking: BLUE.** The only male build.\n"


# --- THE PROMPT ---


def test_the_observation_arrives_before_the_production_notes():
    """
    The order is the safeguard, not a preference.

    Put the character sheet first and it reads as a list of things to find;
    put the observation first and it reads as the evidence, which is what it
    is. Nothing else in this pass prevents a model naming a character it was
    primed with, and a wrong name is not visibly wrong later.
    """
    backend = ScriptedBackend()
    knowledge = ProjectKnowledge(production=PRODUCTION, terminology="EWS: extreme wide shot")

    Interpreter(backend, knowledge).interpret(an_observation())
    prompt = backend.prompts[0]

    assert prompt.index("=== WHAT WAS OBSERVED ===") < prompt.index("=== PRODUCTION NOTES ===")
    assert prompt.index("=== WHAT WAS OBSERVED ===") < prompt.index("=== SHOT TERMINOLOGY ===")


def test_the_observed_fields_are_sent_rather_than_the_raw_reply():
    """
    The raw reply may carry a preamble, a code fence or an apology, and none of
    that is evidence about the picture.
    """
    backend = ScriptedBackend()
    observation = an_observation(raw="Sure! Here is my description:\n```\nframing: ...\n```")

    Interpreter(backend, ProjectKnowledge()).interpret(observation)
    prompt = backend.prompts[0]

    assert "open water" in prompt
    assert "Sure! Here is my description" not in prompt


def test_every_field_is_asked_for():
    backend = ScriptedBackend()

    Interpreter(backend, ProjectKnowledge()).interpret(an_observation())

    for name in INTERPRETATION_FIELDS:
        assert f"{name}:" in backend.prompts[0]


def test_a_show_with_no_knowledge_is_still_interpreted():
    """
    The breakdown case: no character sheet yet, and this is how the show gets
    one. Nobody is named, every shot is still described.
    """
    backend = ScriptedBackend("shot_size: EWS\nsummary: EWS of a boat on open water.")

    interpretation = Interpreter(backend, ProjectKnowledge()).interpret(an_observation())

    assert "PRODUCTION NOTES" not in backend.prompts[0]
    assert interpretation.summary == "EWS of a boat on open water."


def test_an_observation_that_reported_nothing_says_so():
    """
    Better than an empty section, which reads as a picture with nothing in it
    rather than as a description that failed.
    """
    backend = ScriptedBackend()

    Interpreter(backend, ProjectKnowledge()).interpret(Observation())

    assert "(nothing was reported)" in backend.prompts[0]


# --- READING THE REPLY ---


def test_the_plain_case():
    interpretation = parse_reply(
        "shot_size: EWS\n"
        "shot_type: Single\n"
        "camera_move: Crane\n"
        "characters: Rowan\n"
        "evidence: Rowan: plain blue figure, only male build in the cast\n"
        "location: open water\n"
        "summary: EWS single — Rowan at the controls of a small boat.\n"
    )

    assert interpretation.shot_size == "EWS"
    assert interpretation.camera_move == "Crane"
    assert interpretation.characters == ["Rowan"]
    assert interpretation.evidence["Rowan"].startswith("plain blue figure")
    assert interpretation.summary.startswith("EWS single")


def test_a_decline_is_kept_as_an_absence_rather_than_as_a_word():
    """
    "unknown" must not survive into the text the matcher compares. Carried
    through as a name it would match every other unplaceable figure in the
    batch — a wrong number proposed confidently, which is the one outcome worse
    than no number at all.
    """
    interpretation = parse_reply(
        "shot_size: unclear\ncharacters: unknown\nlocation: n/a\nsummary: A figure in a boat."
    )

    assert interpretation.shot_size == ""
    assert interpretation.characters == []
    assert interpretation.location == ""
    assert interpretation.summary == "A figure in a boat."


def test_a_figure_nobody_could_place_does_not_displace_one_who_was():
    """
    Two figures, one named. The named one has to survive the other's decline,
    in the order they were observed.
    """
    interpretation = parse_reply("characters: Rowan, unknown, Marlow")

    assert interpretation.characters == ["Rowan", "Marlow"]


def test_a_reply_wrapped_in_a_code_fence_still_reads():
    interpretation = parse_reply("```\nshot_size: MS\nsummary: A medium shot.\n```")

    assert interpretation.shot_size == "MS"


def test_a_reply_with_a_preamble_still_reads():
    """A batch of forty must not fail because one reply was chatty."""
    interpretation = parse_reply(
        "Based on the description provided, here is my reading:\n\nshot_size: WS\n"
    )

    assert interpretation.shot_size == "WS"


def test_markdown_emphasis_around_a_field_name_is_ignored():
    """Asked for `field: answer`, a model will often bold the field."""
    interpretation = parse_reply("**shot_size:** CU\n- camera_move: static\n")

    assert interpretation.shot_size == "CU"
    assert interpretation.camera_move == "static"


def test_a_field_answered_over_several_lines_is_kept_whole():
    """
    Evidence is routinely a line per character, and taking only the first would
    throw away every identification after the first one.
    """
    interpretation = parse_reply(
        "characters: Rowan, Marlow\n"
        "evidence:\n"
        "- Rowan: plain blue figure, broader shoulders\n"
        "- Marlow: plain orange figure, low to the ground on wheels\n"
        "location: the seafront\n"
    )

    assert set(interpretation.evidence) == {"Rowan", "Marlow"}
    assert "wheels" in interpretation.evidence["Marlow"]
    assert interpretation.location == "the seafront", "the next field still ends the last one"


def test_evidence_that_is_not_in_name_detail_form_is_dropped_rather_than_mangled():
    """
    Half-parsed evidence would show beside an identification as though it
    justified it. An empty evidence map is honest; a wrong one is not.
    """
    interpretation = parse_reply("evidence: the colours matched the blocking convention")

    assert interpretation.evidence == {}


def test_a_reply_that_answered_nothing_gives_an_empty_interpretation():
    """Empty rather than raising: one unreadable shot must not stop thirty-nine."""
    assert parse_reply("I'm not able to help with that.") == Interpretation()
