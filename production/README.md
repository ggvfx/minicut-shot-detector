# Production Knowledge

Put your show's `production.md` in this folder. The Identifier tab reads it on
every run — you write it once, rather than attaching it each session. Edit it
while the app is open and press **Re-read**.

Everything here except this README is gitignored, so your show's material never
ends up in the repository.

## What goes in it

One file, organised under three headings. Each `##` under a heading is one
entry, and the app counts them back to you — "3 characters, 2 props, 4
environments" — so you can see at a glance that it was read the way you meant.

- **`# Characters`** — who is in the show
- **`# Props`** — objects that matter enough to name
- **`# Environments`** — the places scenes happen

All of it is optional. Without the file every shot is still described, just
without anything being named, which is exactly what you want when starting a
breakdown for a show that has no list yet.

## Writing it

Plain markdown, read by a language model rather than parsed. Write it for a
person and it will work.

Two things worth knowing:

**Lead with what tells them apart.** For identification, the useful detail is
what separates this character from the others in the scene, not an exhaustive
costume description. "The only one on skates" does more work than three
paragraphs about a jacket.

**Say how each one looks in each representation.** A show is rarely all in one
state. If a character is a red mannequin in a CG blockout and a woman with blue
hair in a final render, saying so is what lets both be recognised as the same
person.

## Example

```markdown
# Characters

## Tess
Twenty-something woman, bright blue hair, always on rollerskates.

**Tells her apart:** the only character on skates, in any version.

**In CG blockout:** a red mannequin, on skates. The others are grey.

## Marcus
Older man, heavy build, long dark coat and a flat cap.

**Tells him apart:** the coat silhouette, and he is the tallest character.

**In CG blockout:** a tall grey mannequin with a coat shape over it.

# Props

## The radio
A boxy portable radio with a bent aerial, carried by Marcus.

**In CG blockout:** a grey box with a thin rod on top.

# Environments

## The shoreline
Open beach, wet sand, low breakwaters running into the sea. Overcast.

**In CG blockout:** a flat plane with regular block shapes to the horizon.
```

## What is not here

**Film terminology** — what CS, OTS and "dolly in" mean — ships with the app
and is not your file. It changes almost never, and a terminology file quietly
broken would mean a whole batch described in words that match no shot list.
