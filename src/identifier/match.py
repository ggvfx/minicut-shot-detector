"""
Pass 3 — Matching.

Compares an interpreted shot against every shot list entry and decides which
one it is, or decides it cannot tell.

**Confidence is derived here, never asked of a model.** A model asked for 0.85
is reporting a feeling. What makes a match trustworthy is *which attributes
agreed*: characters and location and shot size all matching is a different
claim from only the characters matching, and the score has to be able to say
so. The same comparison writes the note a person reads — "characters and
location match, shot size differs" — and decides when to stay quiet.

A shot that cannot be placed is left unnamed. Guessing produces a wrongly named
file, which is worse than an obviously unnamed one and much harder to notice
three weeks later.

SKELETON. Signatures and docstrings only.
"""

from typing import List

from src.identifier.models import Candidate, Interpretation, ShotListEntry

# --- WHAT COUNTS, AND FOR HOW MUCH ---

# Characters are weighted hardest because they are the most discriminating
# thing in a shot list: two shots of the same pair of people in the same place
# are common, two shots of a *different* pair rarely confusable. Shot size is
# weighted lightest because it is the most subjective judgement in the chain.
#
# These are a starting point to be measured against real shot lists, not
# settled values.
ATTRIBUTE_WEIGHTS = {
    "characters": 0.40,
    "location": 0.25,
    "action": 0.20,
    "shot_size": 0.10,
    "camera_move": 0.05,
}

# Below this, nothing is proposed and the shot is left for a person.
MINIMUM_CONFIDENCE = 0.5

# How far clear of the runner-up the best candidate must be. A top score that
# two entries share is not a match — it is the tool saying it cannot tell them
# apart, which is worth reporting honestly.
MINIMUM_MARGIN = 0.15


def compare(interpretation: Interpretation, entry: ShotListEntry) -> Candidate:
    """
    Scores one shot against one shot list entry, attribute by attribute.

    Notes:
        An attribute missing from the reference is not a disagreement and must
        not be counted as one. A thumbnail has no camera move; a one-line
        description may say nothing about location. Scoring those as failures
        would punish every candidate equally and drag real matches below the
        threshold. The weights of absent attributes are redistributed across
        the ones both sides actually have.
    """
    # PSEUDOCODE
    # 1. For each weighted attribute present on both sides, decide agreement.
    # 2. Record each comparison with both values, for the note.
    # 3. Redistribute the weight of absent attributes across those compared.
    # 4. Return the Candidate with its attribute list and score.
    raise NotImplementedError


def best_match(interpretation: Interpretation, entries: List[ShotListEntry]) -> List[Candidate]:
    """
    Ranks every entry for one shot.

    Returns:
        Candidates, best first. The full ranking is kept rather than only the
        winner, because the runner-up is what a person needs when they
        disagree with the top answer — and because the gap between first and
        second is itself evidence.
    """
    # PSEUDOCODE
    # 1. Compare against every entry.
    # 2. Sort by score, best first.
    raise NotImplementedError


def decide(candidates: List[Candidate]) -> tuple:
    """
    Turns a ranking into a proposal, or into an honest silence.

    Returns:
        (shot_number or None, confidence, note). None where the best score is
        below MINIMUM_CONFIDENCE, or where it is not clear of the runner-up by
        MINIMUM_MARGIN — two entries that score alike means the tool cannot
        tell them apart, and saying so is more useful than picking one.

    Notes:
        The note is written from the attribute comparison, not by a model. It
        names what agreed and what did not, so a person can check the claim
        rather than weigh a number they have no way to judge.
    """
    # PSEUDOCODE
    # 1. No candidates -> (None, 0.0, "nothing to match against").
    # 2. Below MINIMUM_CONFIDENCE -> (None, score, what failed to agree).
    # 3. Within MINIMUM_MARGIN of the runner-up -> (None, score, name both).
    # 4. Otherwise -> (number, score, what agreed and what did not).
    raise NotImplementedError
