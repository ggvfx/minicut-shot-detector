# Production Knowledge

Put your show's markdown in this folder. The Identifier tab reads it on every
run — you write it once, rather than attaching it each session.

Everything here except this README is gitignored, so your show's material never
ends up in the repository.

## The files

**`characters.md`** — who is in the show, and **how each one appears in each
representation**. That last part is what makes the tab work: it is what lets a
red mannequin on rollerskates in a CG blockout be recognised as the same person
as a woman with blue hair in a final render.

**`terminology.md`** — how *this* facility names shot sizes, types and camera
moves. "Top of head to shoulders" is a CS here and a BCU somewhere else, and
both are correct. Holding it in a file you own is what makes the same
observation produce the same term on every shot of a batch, instead of whatever
the model happens to say that time.

Both are optional. Without them the tab still describes every shot — it just
describes them in plain words and does not name anyone, which is exactly what
you want when starting a breakdown for a show that has no character list yet.

Props and environments will follow the same pattern. They are not built yet.

## Writing them

Plain markdown. They are read by a language model, not parsed, so write them
for a person and they will work.

One thing worth knowing: for identification, what does the work is the
**distinguishing** detail — what separates this character from the others in
the scene, and how they look across blockout versus final. Exhaustive costume
description helps a human and mostly just adds length here. Lead with what
tells them apart.

### characters.md

```markdown
# Characters

## Tess
Twenty-something woman, bright blue hair, always on rollerskates.
Wears a patched yellow jacket over a grey vest.

**In CG blockout:** a red mannequin, always on skates. The skates are the
reliable tell — the other mannequins are grey.

## Marcus
Older man, heavy build, long dark coat and a flat cap.

**In CG blockout:** a tall grey mannequin in a coat. Distinguished from the
other grey mannequins by the coat silhouette and his height.
```

### terminology.md

```markdown
# Shot terminology

## Shot sizes
- **BCU** — eyes to chin
- **CU** — top of head to just below the chin
- **CS** — top of head to shoulders
- **MS** — waist up
- **WS** — full body, room around them
- **EWS** — figure small in frame, location is the subject

## Shot types
- **OTS** — over the shoulder; a head or shoulder blocks part of the frame
- **2-shot** — two subjects sharing the frame
- **POV** — the camera is a character's eyeline

## Camera moves
- **Static** — the frame does not move
- **Pan** — the frame rotates horizontally
- **Dolly in / out** — the camera travels toward or away from the subject
- **Track** — the camera travels alongside the subject
```
