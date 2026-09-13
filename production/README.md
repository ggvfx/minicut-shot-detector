# Production Knowledge

Put your show's markdown in this folder. The Identifier tab reads it on every
run — you write it once, rather than attaching it each session.

Everything here except this README is gitignored, so your show's material never
ends up in the repository.

## The file

**`characters.md`** — who is in the show, and **how each one appears in each
representation**. That last part is what makes the tab work: it is what lets a
red mannequin on rollerskates in a CG blockout be recognised as the same person
as a woman with blue hair in a final render.

It is optional. Without it the tab still describes every shot — it just
describes them without naming anyone, which is exactly what you want when
starting a breakdown for a show that has no character list yet.

Props and environments will follow the same pattern. They are not built yet.

**Film terminology is not here.** What CS and OTS and "dolly in" mean ships
with the app, in `src/identifier/templates.py`. It lives apart from this folder
because it changes almost never, and a terminology file quietly broken would
mean a whole batch described in words that match no shot list. Edit it there if
your facility genuinely names things differently.

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
