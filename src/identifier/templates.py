"""
Film Terminology.

The vocabulary the interpretation pass translates observations into. Shipped
with the app rather than left in the user's production folder, because it is a
different kind of thing from a character sheet: a show's characters change
every job, while what "CS" means changes almost never.

Exposing it alongside the character sheet would invite someone to edit the one
thing here that does not need editing, and a terminology file quietly broken is
a whole batch described in words that match no shot list.

Editable by anyone who genuinely needs to — a facility that calls a close shot
a BCU can change it here — and out of the way of anyone who does not.

Held as a constant rather than a data file so it always ships with the app,
following the `templates.py` convention in CODE_STYLE.md for reusable
definitions that are data rather than behaviour.
"""

# --- THE VOCABULARY ---

# Written as prose rather than as a table, because its reader is a language
# model: it goes into the interpretation prompt as-is. Each term is defined by
# what would be *observed*, not by another term — "top of head to shoulders"
# can be matched against a description, where "a close shot" cannot.
FILM_TERMINOLOGY = """
# Shot sizes

- **BCU** — big close up. Eyes to chin, or a detail of a face.
- **CU** — close up. Top of head to just below the chin.
- **CS** — close shot. Top of head to shoulders.
- **MCU** — medium close up. Head and upper chest.
- **MS** — mid shot. Waist up.
- **MWS** — medium wide. Knees up.
- **WS** — wide shot. The whole figure, with room around it.
- **EWS** — extreme wide. The figure is small in frame; the location is the
  subject.

# Shot types

- **OTS** — over the shoulder. A head or shoulder occupies the foreground and
  partly blocks the frame, with the subject beyond it.
- **2-shot** — two subjects sharing the frame.
- **3-shot** — three subjects sharing the frame.
- **Group shot** — four or more subjects sharing the frame.
- **POV** — the camera stands where a character's eyes would be.
- **Insert** — a detail, usually an object or a hand, with no face in frame.
- **Establisher** — a wide that sets a location before a scene plays in it.

# Camera moves

- **Static** — the framing does not change across the shot.
- **Pan** — the frame rotates horizontally; the camera does not travel.
- **Tilt** — the frame rotates vertically; the camera does not travel.
- **Dolly in** — the framing tightens as the camera travels toward the subject.
- **Dolly out** — the framing widens as the camera travels away.
- **Track** — the camera travels alongside a moving subject, holding its size.
- **Crane** — the camera rises or falls.
- **Handheld** — the frame moves constantly and irregularly throughout.
- **Zoom** — the framing changes without the camera appearing to travel.
"""
