# Architecture Overview — Minicut Shot Detector

**Design principle:**
Each stage is decoupled and independently testable. The pipeline only
coordinates execution order.

**Three tabs, two of them workflows.** Splitter and Identifier are the jobs;
Setup is everything you do once, kept out of both so a panel nobody reads does
not sit above the work people do daily. Each workflow tab carries a one-line
status strip instead, and links to Setup when something is wrong.

| | Splitter | Identifier |
|---|---|---|
| Takes | one mini cut | a folder of single-shot files |
| Gives | one file per shot | shot numbers, or a breakdown to seed a database |
| Nature | **deterministic** — same input, byte-identical boundaries | **judgement** — a model proposes, a person decides |
| Needs | ffmpeg, encoders, PySceneDetect | ffmpeg and a model backend — neither of the others |

That last row is why each tab has its own dependency panel rather than sharing
one: showing each the other's requirements puts rows in front of people who
cannot act on them.

**They do not depend on each other.** The identifier takes any folder of video
files, whether or not the splitter made them. If a splitter sidecar happens to
be beside them it may be read for frame ranges and timecodes, but it is never
required — most batches will arrive from somewhere else entirely.

**Splitter data flow:**

Probe → Mezzanine → Proxy → Detect → Review → Cut → Validate → Sidecar

The pipeline has two entry points, because a person sits in the middle of it:
`prepare()` does everything up to the proxy, and `run()` takes the reviewed
boundaries through to the sidecar.

**Identifier data flow:**

Frames → Observe → Interpret → Match → Review → Rename *or* Export

Three model passes, and the split between them is the whole design. See
[The identifier](#the-identifier) below.

---

## Stage details

### 1. Probe — `SourceProbe` in `src/media/probe.py`

- Reads frame rate, duration, resolution, codec and start timecode via `ffprobe`
- Refuses variable frame rate sources, where the frame-to-time mapping is
  unstable and every boundary would drift
- Finds letterbox/pillarbox bars with `cropdetect`, sampled at several points,
  and reports them for confirmation — never asks the user to type a mask in
- Estimates the disk the job needs, before the job rather than after the drive fills

Produces a `SourceInfo`.

### 2. Detect — `src/splitter/`

Two passes over the mezzanine, both from PySceneDetect, neither a neural
network. Each compares a frame with the one before it; they differ in what they
compare the difference against:

- `SceneDetectPass(CONTENT)` — a fixed threshold.
- `SceneDetectPass(ADAPTIVE)` — a rolling average of the surrounding frames, so
  a cut has to stand out from its neighbours.

Both run because measuring them on real deliveries showed each finding real
cuts the other missed, in opposite conditions: Adaptive misses cuts in
continuously high-motion footage, Content false-positives on near-identical
frames in flat previz. The union is used, and anything only one of them found
is marked for a human glance.

There is no third pass, and no neural one. A TransNetV2 detector was designed
and skeletoned, then **removed** once the two classical passes were judged on
real CG renders and AI generations: they get the cuts, fast cuts are where they
trip, and correcting those by hand is quick. The skeleton is in git history and
the reasoning is in TODO.md under Deferred. What would bring it back is gradual
transitions — dissolves, fades and wipes — which a frame-to-frame difference is
not built to see.

Each pass produces a list of `Boundary`, carrying the names of the detectors
that found it.

### 3. Reconcile — `src/splitter/reconcile.py`

Plain functions — nothing to hold between calls.

- Matches boundaries between the two passes within a two frame tolerance
- Both fired → confident. One fired → kept, flagged for review.
- Converts boundaries into `Shot` ranges that tile the source exactly

There is no flash-frame filter. A camera flash can read as two cuts a few
frames apart, and a minimum shot length would merge them back — but with a
person reviewing every boundary, a spurious short shot is one click to remove,
while a filter that quietly drops a genuinely quick cut leaves nothing to
notice. Nothing in real footage has asked for it yet. See TODO.md, Deferred.

### 3.5 Review — `ProxyBuilder` in `src/media/proxy.py`, and the front end

- Builds a 640px all-intra h264 proxy from the mezzanine, with each frame's
  number burned into the corner
- The browser plays that rather than the source: long-GOP seeking lands near a
  frame rather than on it, and h265 playback depends on the viewer's hardware
- The burned-in number is a check, not decoration — the player's idea of the
  current frame and the picture's own can be compared at a glance
- Markers are placed and removed here. Detection fills them in; it never
  replaces the person

### 4. Cut — `src/media/`

- `MezzanineBuilder` — re-encodes the source once into an all-intra version of
  **its own codec** (h264 in, h264 out; h265 in, h265 out), because
  `ffmpeg -c copy` can only cut on keyframes and would otherwise move a
  boundary by up to a GOP length, silently
- `ShotSplitter` — stream-copies each shot out of the mezzanine, landing exactly
  on the requested frame, into the source's own container

One file per shot is the entire output of this stage. Thumbnails, contact
sheets and stills belong to the identifier tab, not here.

The single re-encode is unavoidable: in h264 and h265 a file can only start on
a keyframe, so cutting the original data can only land where keyframes already
are. Verified by hand — 30 frames requested out of an all-intra mezzanine gives
30 frames, pixel-identical.

### 5. Validate — `src/splitter/`

- **Integrity:** durations sum to the source, no gaps, no overlaps, correct
  bounds. Proves the numbers add up.
- **Boundary frames (default):** hashes the first and last frame of every shot
  against the mezzanine. Proves the pixels add up where it matters — shots are
  stream copies, so their interiors cannot change and every realistic failure
  moves an edge frame.
- **Full round trip (implemented, not offered):** rejoins every shot and
  compares every frame. It decodes the whole job twice and writes a second copy
  of the mezzanine, and it catches the same class of error the boundary hashes
  already catch — shots are stream copies, so a corrupt interior is not a
  failure mode that occurs. It stayed in the code with its tests, but the UI
  checkbox came out for v1. `POST /api/split` still takes `full_round_trip`, so
  putting it back is a front-end change only.

The two modules split on whether a check needs ffmpeg. `integrity.py` holds
the arithmetic as plain functions — no toolchain, no files, nothing decoded —
so it runs in milliseconds and its tests pass on a machine with no ffmpeg at
all. `validator.py` holds everything that decodes frames, and `validate_job()`
combines the two into one verdict.

Any failure blocks the job and surfaces in the UI. This stage never
warns-and-continues, and it ships with v1.

### 6. Sidecar — `src/core/sidecar.py`

One JSON file per job: the shots with frame and timecode boundaries, the
validation outcome, and the resolved environment that produced them — ffmpeg
build and the versions of what ran the detection.

Written whether the job passed or failed — a failed job's sidecar is the most
useful thing to look at when working out why. Reading sidecars back belongs to
the identifier tab and is not built here.

---

## The identifier

**Not built. This is the agreed design, not a description of code.**

It does two jobs that share one expensive step:

```
                                  ┌─► match to a shot list ──► rename the files
frames ─► observe ─► interpret ───┤
                                  └─► export ──────────────► CSV + thumbnails
```

The first is the point of the tab: give a mini cut's shots the shot numbers
production already uses, so they can be submitted against the right names. The
second falls out of it almost free — the same descriptions, exported instead of
matched, so a new project's shots can be entered into a database from a blockout
without typing them all.

### Why three passes and not one

This is the central decision, and everything else follows from it.

**1. Observe — vision model, frames in, plain text out.**

It is asked for *observables against a fixed schema* and nothing else: how many
people are in frame, where the frame cuts the main subject, whether something
in the foreground partly blocks the view, which way the subject faces, the
setting, and what changes across the frames.

It is **not** asked for film terminology. A model asked for "the shot size"
returns some averaged internet convention applied inconsistently across forty
shots — and inconsistent vocabulary is fatal when the next step is comparing
text to text. It is also given **no project knowledge at all**: a model told
that Tess has blue hair will find blue hair.

**2. Interpret — text model, no images.**

Turns observations into the project's own vocabulary, using two sources of
knowledge that are deliberately kept apart because they change at completely
different rates:

| Source | Turns | Who owns it |
|---|---|---|
| `templates.FILM_TERMINOLOGY` | "top of head to shoulders", "a shoulder blocking frame left" → `CS`, `OTS` | ships with the app, **never shown** |
| `production/production.md` | "red mannequin on rollerskates" → "likely Tess" | the production, read every run |

A show's characters change every job; what "CS" means changes almost never.
Putting the terminology in front of the user would only invite editing the one
thing that does not need editing, and a terminology file quietly broken is a
whole batch described in words that match no shot list.

The production file is organised under `# Characters`, `# Props` and
`# Environments`, and the entries under each are counted back to the user —
"3 characters, 2 props, 4 environments". That count is the cheapest way to see
the file was read the way it was meant: a heading typed at the wrong level
shows up as a category with nothing in it.

Both the observation and what it was read as are kept. A wrong identification
is then visible rather than silent — the same principle as the frame numbers
burned into the review proxy: make the check something you can see.

Character sheets are detailed, and they describe one identity across
representations — how someone looks in a final render, and that in a CG
blockout they are a particular mannequin. Keeping that out of the observation
pass is what stops the sheet writing the answer.

**3. Match — text model, no images.**

Compares interpreted attributes against the shot list, attribute by attribute.
**Confidence is derived from which attributes agree**, never asked of a model:
matching characters *and* location *and* shot size is a different thing from
matching only the characters, and saying so is what makes the number mean
anything. The same comparison writes the notes — "characters and location
match, shot size differs" — and decides when to stay silent. **A shot it cannot
place is left unnamed for a person to handle.**

This also solves the thumbnail case. A reference thumbnail is a still, so it has
no camera move; matching simply does not compare an attribute the reference
could never have.

### What this buys

- Only pass 1 needs images or a vision model, it runs **once per shot**, and its
  output is cached beside the files. Everything a user iterates on — fixing the
  terminology, adding a character, correcting the shot list — re-runs passes 2
  and 3 over cached text in seconds.
- The vocabulary is the project's, not the model's, so the same observation
  always produces the same term. Deterministic where it can be.
- Passes 2 and 3 are text-only, which is what makes the backend question below
  answerable.

### Model backends

One adapter interface, configured per pass: **give a prompt and optionally some
images, get text back.** Three implementations — a CLI command, an HTTP API, or
a local runtime.

Configured in `settings.json` beside the app — gitignored, with
`settings.example.json` as the tracked template — so a facility sets one up
once and hands the whole folder over. It never holds a credential: the config
names the *environment variable* holding a key, and the key is read at the
moment of the call.

**The CLI and API paths are the product. Local is the option.** This is built
to be handed to people whose machines are nothing like the one it was written
on, and no design decision may assume local inference — not speed, not context
size, not "we can just run it again". A machine with no GPU and a configured
command is a fully supported setup, reported green by the environment panel.

Vision and text are configured **separately**, because they will often differ.
A studio using an agentic CLI for text may have to point the observe pass
somewhere else; someone with one API key points both at it; someone with a big
graphics card runs both locally. Same code.

No model is committed to this repo. The smallest useful local vision model is
~1.7 GB, which makes it a download, a version to track and a thing to go wrong
— and that arrangement was already tried and deleted once, when the TransNetV2
export lived in `models/`.

**Frames are small on purpose** — a few hundred pixels, from the same ffmpeg
machinery as the 640px review proxy. Nothing about judging framing needs 1920
pixels, and small frames make API calls cheap, local inference quick, and fit
CLI tools that only accept preview-sized images.

### Two things the splitter settled that this reverses, deliberately

**Progress must be reported.** The splitter shows only that work is happening,
because its worst realistic case is 44 seconds. A batch here is 1–40 shots at
model speed, so the table fills in row by row as results land. Same reasoning,
opposite answer, because the measurement is different.

**Renaming is the only destructive thing either tab does.** It happens on
explicit approval, never automatically, and writes a log beside the files so it
can be undone.

---

## Module map

Two features over shared foundations. Anything either tab could want lives in
`core/` or `media/`; anything only one tab wants lives in that tab's package.
Where a thing belongs is then a question with an answer, rather than a habit.

```
src/
├── core/          SHARED by both tabs: config, models, utils, timecode, ffmpeg,
│                 environment, sidecar. One file each, so every setting and
│                 every data shape has exactly one place to look.
├── media/         SHARED: probing, frames, mezzanine, proxy, extraction, workspace
├── splitter/      detection, reconciliation, validation, the splitter pipeline
├── identifier/    observation, interpretation, matching, renaming, export     (not built)
├── backends/      the model adapters — CLI, HTTP API, local runtime
└── ui/            the app, one routes module per tab, and the front end
```

**The restructure is a task, not a description.** Today `detection/`,
`validation/` and `pipeline.py` sit at the top of `src/`, which was right when
there was one tab and becomes misleading with two. Moving them under
`splitter/` is mechanical and covered by the existing suite — see TODO.md 6.1.

| Path | Holds |
|---|---|
| `main.py` | Entry point — starts the server, opens the browser |
| `src/splitter/pipeline.py` | `SplitterPipeline` — stage order and failure handling. No processing logic. |
| `src/core/config.py` | **Shared.** Every constant and both tabs' per-run settings objects |
| `src/core/models.py` | **Shared.** Every data model, banded by which tab uses it |
| `src/core/utils.py` | **Shared.** Helpers needed in more than one module |
| `src/core/templates.py` | **Shared.** Per-platform install instructions — data, not behaviour |
| `src/core/ffmpeg_tools.py` | `MediaToolchain` — the only place a subprocess is run |
| `src/core/timecode.py` | `Timecode` — the only place frames become time |
| `src/core/environment.py` | `EnvironmentChecker` — a dependency panel per tab |
| `src/core/sidecar.py` | Sidecar read and write |
| `src/media/probe.py` | `SourceProbe` — source inspection and crop detection |
| `src/media/mezzanine.py` | `MezzanineBuilder` — all-intra re-encode in the source's codec |
| `src/media/proxy.py` | `ProxyBuilder` — the small numbered proxy the player scrubs |
| `src/media/splitter.py` | `ShotSplitter` — per-shot extraction |
| `src/media/workspace.py` | `.minicut-work/` — its naming, and what may be deleted |
| `src/splitter/scene_detect.py` | `SceneDetectPass` — the two PySceneDetect passes |
| `src/splitter/reconcile.py` | Merge, and convert boundaries to shots |
| `src/splitter/integrity.py` | Shot list arithmetic — plain functions, no ffmpeg |
| `src/splitter/validator.py` | `JobValidator` — the checks that decode frames |
| `src/backends/adapter.py` | The interface every backend implements |
| `src/backends/transport.py` | The HTTP itself — the one place a socket opens |
| `src/backends/command.py` | A configured CLI — the default path |
| `src/backends/http_api.py` | An HTTP endpoint with a key from the environment |
| `src/backends/local.py` | A local runtime, for machines that can |
| `src/backends/availability.py` | The backend rows in the dependency panel |

| `src/identifier/knowledge.py` | Reading the production's file, and counting what is in it |
| `src/identifier/templates.py` | `FILM_TERMINOLOGY` — the vocabulary, never shown to the user |

Not built, and listed so the shape is agreed before anything is written:

| Path | Would hold |
|---|---|
| `src/identifier/frames.py` | Small sample frames out of a shot, via ffmpeg |
| `src/identifier/observe.py` | Pass 1 — the observation schema, and the only images |
| `src/identifier/interpret.py` | Pass 2 — observations into the project's vocabulary |
| `src/identifier/shotlist.py` | Reading a shot list: CSV, text, or a thumbnail folder |
| `src/identifier/match.py` | Pass 3 — attribute comparison, and derived confidence |
| `src/identifier/rename.py` | Applying names, and the log that undoes them |
| `src/identifier/export.py` | The CSV and thumbnails a database is seeded from |
| `src/identifier/pipeline.py` | `IdentifierPipeline` — stage order and caching. No processing logic. |

| Path | Holds |
|---|---|
| `src/ui/server.py` | The app, the page, the static mount, the wiring |
| `src/ui/runtime.py` | The toolchain and checker every router shares |
| `src/ui/routes/setup.py` | What is installed, and which model each pass uses |
| `src/ui/routes/splitter.py` | Probe, prepare, proxy, split, working files |
| `src/ui/routes/identifier.py` | Production knowledge, and Phase 7's routes |
| `src/ui/routes/files.py` | The path picker, shared by both tabs |
| `src/ui/browse.py` | Directory listing the picker route calls |
| `src/ui/static/main.js` | Wiring — imports the rest, attaches every listener |
| `src/ui/static/state.js` | The one object holding what the page knows |
| `src/ui/static/source.js` | Inspect and analyse |
| `src/ui/static/player.js` | Review proxy, transport, timeline, marks, keyboard |
| `src/ui/static/splitting.js` | Split, and the job table it produces |
| `src/ui/static/work.js` | Reclaimable working files |
| `src/ui/static/picker.js` | Path picker |
| `src/ui/static/environment.js` | Dependency panel |
| `src/ui/static/ui.js` | Display helpers used by more than one module |
| `src/ui/static/tabs.js` | Switching, and telling a tab it became visible |
| `src/ui/static/identify.js` | The identifier tab: models, knowledge, and the job |
| `src/ui/static/setup.js` | The setup tab: dependency panels and install guides |

Each tab has **its own environment panel**, and they are told different things:
the splitter needs encoders and PySceneDetect and no model, the identifier
needs a model and neither of those. Showing each the other's requirements would
put rows in front of people who cannot act on them. `/api/environment` takes a
`tab`, and the report is cached per tab.

The identifier's rows for the model backends **gate that tab** — a user
standing in it with no model can do nothing — which is why `advisory` is
decided by the caller rather than being a property of the row.

`state.js` stays one object, banded per tab. The tabs share `environment.js`,
`picker.js` and `ui.js` unchanged.

---

## Working files

Everything a job needs but nobody asked for goes in `.minicut-work/` inside the
output directory: the mezzanine, the review proxy, and the scratch the round
trip uses. The delivery folder holds the shots and the sidecar, and nothing
else.

The folder is deleted when a job passes and kept when one fails, so a failure
leaves the mezzanine to investigate with. Its path is derived from the output
directory rather than remembered between requests, which is what lets
`prepare()` and `run()` be separate calls without the server holding session
state.

That leaves one gap, and it is filled by reporting rather than by tidying up
automatically. A source that is analysed and then abandoned keeps its mezzanine
— roughly a gigabyte for a few minutes of 1080p — because the whole point of
preparing first is that the encode survives review. Nothing deletes it, so
trying four files and splitting one quietly spends four gigabytes.

`src/media/workspace.py` owns this. `reclaimable_work()` and `clear_work()`
measure and remove those leftovers, and
the Output panel shows the total with a Clear button whenever there is
something to reclaim. **The source currently open is never included** — its
mezzanine is what the split will cut from. Ownership is worked out by stripping
the suffix that was added (`reel_02_mezzanine.mp4` → `reel_02`) rather than by
matching name prefixes, so `reel_02` cannot claim `reel_02_extra`'s files.

Nothing is cleared without being asked. These files are rebuildable, but only
by sitting through the encode again, which makes silently deleting them a worse
trade than a line of text.

---

## Dependency direction

Imports point one way only, which is what keeps any stage testable on its own:

```
core/models.py        imports nothing of ours
core/config.py        may import models
core/utils.py         standard library only

All three are SHARED by both tabs. One models file, one config file, one utils
file — so "what shape is a Shot?" and "what does this setting default to?"
each have exactly one place to look, however many features the app grows.
core/ffmpeg_tools.py  standard library only
core/*                may import the above
media/, detection/, validation/   may import core
pipeline.py           may import core and the stage packages
ui/                   may import core and pipeline
```

Nothing imports upward. `ffmpeg_tools.py` lives in `core` rather than `media`
for exactly this reason: the environment checks need it, and core must never
reach into a domain package.

---

## Key terms

- `frame` — integer frame index, 0 at the first frame of the source
- `boundary` — the frame on which a new shot **starts**
- `shot` — an inclusive range, `start_frame..end_frame`
- `timecode` — a display string, derived from frames only at output time
- `mezzanine` — the all-intra intermediate every split is cut from
- `proxy` — the small numbered copy the browser plays during review
- `work dir` — `.minicut-work/`, where the mezzanine and proxy live during a job

---

## Why the boundaries sit where they do

- **`timecode.py` is its own module** because frame rate conversion and
  off-by-one errors are the failure this project is most exposed to, and they
  are far easier to test in isolation.
- **`MediaToolchain` is the only thing that runs a subprocess**, so the resolved
  binary and version are discovered once and recorded in the sidecar.
- **`SplitterPipeline` holds no logic** so any stage can be re-run, replaced or
  tested without the others.
- **`server.py` holds no logic** for the same reason — if a route grows a
  decision, that decision belongs in a stage module.
- **Classes where state is shared across calls, functions where it is not.**
  A detector holds a loaded model; reconciliation and the integrity checks hold
  nothing, so they are functions. The pipeline's first validation therefore
  needs no toolchain at all — it is checking that numbers add up.

---

## Not built yet

The splitter's job is to detect cuts and write one file per shot. Anything
beyond that is deferred until it is actually needed:

- **Per-shot stills** — QC contact sheets and identifier input. Belongs to the
  identifier tab; the shot files themselves are enough to check a boundary.
- **Variable frame rate normalisation** — VFR is detected and refused. Rewriting
  it to constant frame rate is a whole feature, and waits for a real VFR source.
- **Exact frame counting by decode** — a fallback for containers that lie about
  `nb_frames`. Add it the first time one does.
- **Reading sidecars back** — the identifier tab's entry point.
- Identifier tab in any form
- Dissolve / fade / wipe handling — a boundary would become a range
- Excel shot list ingestion and fuzzy matching
- Character reference image matching
- Native packaging
