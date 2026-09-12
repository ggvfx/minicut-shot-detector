# Architecture Overview — Minicut Shot Detector

**Design principle:**
Each stage is decoupled and independently testable. The pipeline only
coordinates execution order. Detection is deterministic — the same input
produces byte-identical boundaries every run.

**Data flow (high level):**

Probe → Detect → Reconcile → Cut → Validate → Sidecar

---

## Stage details

### 1. Probe — `SourceProbe` in `src/media/probe.py`

- Reads frame rate, duration, resolution, codec and start timecode via `ffprobe`
- Rejects or normalises variable frame rate sources, where the frame-to-time
  mapping is unstable and every boundary would drift
- Finds letterbox/pillarbox bars with `cropdetect`, sampled at several points,
  and reports them for confirmation — never asks the user to type a mask in
- Estimates the disk the job needs, before the job rather than after the drive fills

Produces a `SourceInfo`.

### 2. Detect — `src/detection/`

Two independent passes over the same source, with the same `detect()` interface
so reconciliation does not care which produced what:

- `TransNetDetector` — TransNetV2 through ONNX Runtime, producing a transition
  probability per frame. The primary detector, and the only stateful one: it
  holds the loaded session.
- `SceneDetectCrossCheck` — PySceneDetect's `AdaptiveDetector`, comparing
  neighbouring frames statistically. The cross-check.

The second pass is not there to improve accuracy. It is there so the two can
disagree, because a disagreement is what flags a boundary for human review.

Each produces a list of `Boundary`.

### 3. Reconcile — `src/detection/reconcile.py`

Plain functions — nothing to hold between calls.

- Matches boundaries between the two passes within a two frame tolerance
- Both fired → confident. One fired → kept, flagged for review.
- Merges shots below the minimum length: the flash frame filter. Merges are
  recorded on the shot, never applied silently.
- Converts boundaries into `Shot` ranges that tile the source exactly

### 4. Cut — `src/media/`

- `MezzanineBuilder` — transcodes the source once to an all-intra format,
  because `ffmpeg -c copy` can only cut on keyframes and would otherwise move a
  boundary by up to a GOP length, silently
- `ShotSplitter` — stream-copies each shot out of the mezzanine, landing exactly
  on the requested frame
- `StillExtractor` — head, middle and tail frames per shot; QC now, identifier
  input later

### 5. Validate — `JobValidator` in `src/validation/validator.py`

- **Integrity:** durations sum to the source, no gaps, no overlaps, correct
  bounds. Proves the numbers add up.
- **Round trip:** concatenates the splits back together and frame-hash compares
  against the mezzanine. Proves the pixels add up — catching dropped,
  duplicated or misordered frames that no thumbnail would reveal.

Any failure blocks the job and surfaces in the UI. This stage never
warns-and-continues, and it ships with v1.

### 6. Sidecar — `src/core/sidecar.py`

One JSON file per job: the shots with frame and timecode boundaries, the
validation outcome, and the resolved environment that produced them — ffmpeg
build, onnxruntime version, model checksum.

Written whether the job passed or failed. Plain functions, because the
identifier tab will read a sidecar with no toolchain and no config at all.

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
| `src/media/mezzanine.py` | `MezzanineBuilder` — all-intra transcode |
| `src/media/splitter.py` | `ShotSplitter` — per-shot extraction |
| `src/media/stills.py` | `StillExtractor` — per-shot stills |
| `src/detection/transnet.py` | `TransNetDetector` — primary detector |
| `src/detection/scene_detect.py` | `SceneDetectCrossCheck` — cross-check detector |
| `src/detection/reconcile.py` | Merge, filter, convert to shots |
| `src/validation/validator.py` | `JobValidator` — integrity and round trip |
| `src/ui/server.py` | FastAPI routes. The only module that knows about HTTP. |
| `src/ui/browse.py` | Directory listing for the path picker |
| `src/ui/static/` | `index.html`, `app.js`, `styles.css` |
| `scripts/export_transnetv2.py` | One-off build step producing the committed `.onnx` |

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
- `golden set` — hand-labelled true cut frames in `tests/golden/`, the regression suite

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
  A detector holds a loaded model; reconciliation holds nothing.

---

## Not built yet

Deferred deliberately, in this order of likelihood:

- Identifier tab in any form
- Dissolve / fade / wipe handling — a boundary would become a range
- Excel shot list ingestion and fuzzy matching
- Character reference image matching
- Native packaging
