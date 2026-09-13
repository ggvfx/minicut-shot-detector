# Architecture Overview — Minicut Shot Detector

**Design principle:**
Each stage is decoupled and independently testable. The pipeline only
coordinates execution order. Detection is deterministic — the same input
produces byte-identical boundaries every run.

**Data flow (high level):**

Probe → Mezzanine → Proxy → Detect → Review → Cut → Validate → Sidecar

The pipeline has two entry points, because a person sits in the middle of it:
`prepare()` does everything up to the proxy, and `run()` takes the reviewed
boundaries through to the sidecar.

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

### 2. Detect — `src/detection/`

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

### 3. Reconcile — `src/detection/reconcile.py`

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

### 5. Validate — `src/validation/`

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

## Module map

| Path | Holds |
|---|---|
| `main.py` | Entry point — starts the server, opens the browser |
| `src/pipeline.py` | `SplitterPipeline` — stage order and failure handling. No processing logic. |
| `src/core/config.py` | Fixed constants and the per-run `ProjectConfig` |
| `src/core/models.py` | `SourceInfo`, `Boundary`, `Shot`, `ValidationResult`, `JobResult` |
| `src/core/utils.py` | Helpers used by more than one module — checksums, directory creation |
| `src/core/ffmpeg_tools.py` | `MediaToolchain` — the only place a subprocess is run |
| `src/core/timecode.py` | `Timecode` — the only place frames become time |
| `src/core/environment.py` | `EnvironmentChecker` — the dependency panel |
| `src/core/sidecar.py` | Sidecar read and write |
| `src/media/probe.py` | `SourceProbe` — source inspection and crop detection |
| `src/media/mezzanine.py` | `MezzanineBuilder` — all-intra re-encode in the source's codec |
| `src/media/proxy.py` | `ProxyBuilder` — the small numbered proxy the player scrubs |
| `src/media/splitter.py` | `ShotSplitter` — per-shot extraction |
| `src/media/workspace.py` | `.minicut-work/` — its naming, and what may be deleted |
| `src/detection/scene_detect.py` | `SceneDetectPass` — the two PySceneDetect passes |
| `src/detection/reconcile.py` | Merge, filter, convert to shots |
| `src/validation/integrity.py` | Shot list arithmetic — plain functions, no ffmpeg |
| `src/validation/validator.py` | `JobValidator` — the checks that decode frames |
| `src/ui/server.py` | FastAPI routes. The only module that knows about HTTP. |
| `src/ui/browse.py` | Directory listing for the path picker |
| `src/ui/static/main.js` | Wiring — imports the rest, attaches every listener |
| `src/ui/static/state.js` | The one object holding what the page knows |
| `src/ui/static/source.js` | Inspect and analyse |
| `src/ui/static/player.js` | Review proxy, transport, timeline, marks, keyboard |
| `src/ui/static/splitting.js` | Split, and the job table it produces |
| `src/ui/static/work.js` | Reclaimable working files |
| `src/ui/static/picker.js` | Path picker |
| `src/ui/static/environment.js` | Dependency panel |
| `src/ui/static/ui.js` | Display helpers used by more than one module |

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
