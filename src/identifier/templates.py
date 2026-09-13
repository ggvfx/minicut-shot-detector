"""
Film Terminology.

The vocabulary the interpretation pass translates observations into. Shipped
with the app and **never shown to the user**, because it is a different kind of
thing from a production's own knowledge: a show's characters change every job,
while what "CS" means changes almost never.

Exposing it would invite editing the one thing here that does not need editing,
and a terminology file quietly broken is a whole batch described in words that
match no shot list. Someone who genuinely needs to change it can edit this
file; nobody else needs to know it exists.

Drawn from two standard references — Epidemic Sound's guide to camera shots and
MasterClass's guide to camera moves — and written out in terms of what is
*observable* rather than in terms of other jargon.

Held as a constant rather than a data file so it always ships with the app,
following the `templates.py` convention in CODE_STYLE.md for reusable
definitions that are data rather than behaviour.
"""

# --- THE VOCABULARY ---

# Written as prose rather than a table, because its reader is a language model:
# it goes into the interpretation prompt as-is.
#
# Every term is defined by what would be SEEN — where the frame cuts the
# subject, what moves, how many figures — never by another term. "Top of head
# to shoulders" can be matched against an observation; "a close shot" cannot.
# That is the whole reason this file exists rather than asking the model for
# the term directly.
FILM_TERMINOLOGY = """
# Shot sizes

Judged by where the frame cuts the main subject.

- **ECU** — extreme close up. A detail: the eyes, the mouth, a hand. Less than
  a whole face.
- **CU** — close up. The face fills the frame, with little or no background.
  Roughly the top of the head to the chin.
- **MCU** — medium close up. Head and the top of the chest, cut around the
  shoulders or upper chest.
- **MS** — mid shot. Cut at roughly the waist.
- **Cowboy** — cut at roughly mid-thigh. Wider than a mid shot, tighter than a
  medium wide.
- **MWS** — medium wide. Cut at roughly the knees.
- **WS** — wide shot. The whole figure is in frame, head to foot, with space
  around it.
- **EWS** — extreme wide. The figure is small in the frame; the location
  dominates.
- **Establisher** — a wide view of a place with no single subject held, used to
  set where a scene happens.

# How many subjects

- **Single** — one person in frame.
- **2-shot** — two people sharing the frame.
- **3-shot** — three people sharing the frame.
- **Group shot** — four or more.
- **Insert** — no person; an object, a hand, a detail, a screen.

# Shot types

Judged by where the camera is relative to the subject.

- **OTS** — over the shoulder. A head or shoulder sits large in the foreground,
  partly blocking the frame, with the subject beyond it.
- **OTH** — over the hip. As above, but the foreground figure is framed at hip
  height.
- **POV** — point of view. The camera occupies a character's eyeline; what is
  seen is what they would see.
- **High angle** — the camera looks down at the subject.
- **Low angle** — the camera looks up at the subject.
- **Eye level** — the camera is level with the subject's eyes.
- **Overhead** — the camera looks straight down from above.
- **Aerial** — a view from far above the scene, as from a drone or helicopter.
- **Dutch angle** — the horizon is tilted off level.

# Camera moves

Judged by what changes across the shot.

- **Static** — the framing does not change.
- **Pan** — the camera pivots horizontally from a fixed position. The view
  sweeps sideways; the camera does not travel.
- **Tilt** — the camera pivots vertically from a fixed position.
- **Whip pan** — a pan fast enough to blur the picture, usually between two
  parts of a scene.
- **Dolly in / dolly out** — the camera travels toward or away from the
  subject. The framing tightens or widens and the background shifts in
  perspective, unlike a zoom.
- **Truck** — the camera travels left or right through the scene.
- **Track** — the camera travels with a moving subject, holding it at roughly
  the same size in frame.
- **Pedestal** — the whole camera rises or lowers, unlike a tilt where it only
  pivots.
- **Crane** — the camera sweeps high or low through the air, often combining a
  rise with a move across.
- **Arc** — the camera travels around the subject on a curve.
- **Handheld** — the frame moves constantly and irregularly, unstabilised.
- **Zoom** — the framing tightens or widens with no change in perspective,
  because the camera has not travelled.
- **Dolly zoom** — the subject stays the same size while the background
  stretches or compresses. Rare and distinctive.
- **Rack focus** — the camera does not move; focus shifts from one part of the
  frame to another.
"""
