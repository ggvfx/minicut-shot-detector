# Shot Splitter & Identifier

A local web app for breaking down finished video edits ("mini cuts") into their
constituent shots and naming those shots against a supplied shot list.

Two tabs:

1. **Splitter** — load a mini cut, detect shot boundaries, split into individual
   files in an output directory.
2. **Identifier** — load a directory of split shots, describe them, match them
   against a shot list, human-review the matches, rename on approval.

**Current scope: the Splitter only.** Do not build identifier functionality
unless explicitly asked. The identifier is documented here for context so that
splitter outputs are designed to feed it.

---

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI | SSE for progress streaming |
| Frontend | Plain HTML + CSS + vanilla JS | No React, no npm, no build step |
| Serving | FastAPI static files on localhost | User opens in their own browser |
| Detection (primary) | TransNetV2 via ONNX Runtime | Not PyTorch — see below |
| Detection (secondary) | PySceneDetect `AdaptiveDetector` | Cross-check only |
| Media | ffmpeg / ffprobe as subprocesses | Never a Python binding |

### Why ONNX and not PyTorch

TransNetV2 ships as a repo with TF and PyTorch inference paths. We export the
model to ONNX once as a build step and commit the `.onnx` file. This removes a
several-hundred-MB torch dependency, produces identical output, and gets Apple
Silicon acceleration via the CoreML execution provider. Runtime deps are
`onnxruntime` + `numpy`.

### Why not a native app

This is a localhost web app deliberately. No Electron, no Tauri, no PyInstaller,
no code signing, no notarization. Distribution is a folder plus a one-time
`setup.bat` / `setup.command` that creates a venv and installs pinned deps.

---

## Non-negotiables

These are settled decisions. Do not revisit them without asking.

1. **Integer frame numbers everywhere.** Convert to timecode only at output
   boundaries. Floating-point seconds are the single biggest source of
   off-by-one cuts.
2. **Frame-accurate splits.** `ffmpeg -c copy` cuts on keyframes and will
   silently move boundaries by up to a GOP length. Transcode the source once to
   an all-intra mezzanine (ProRes 422 or DNxHR), then stream-copy each split.
3. **The validation stage ships with v1.** It is not a later addition. See below.
4. **The splitter is deterministic.** No LLM, no agent, no adaptive thresholds in
   the detection path. Identical input must produce byte-identical boundaries on
   every run. Judgment work belongs in the identifier tab.
5. **Pinned dependencies.** Exact versions in `requirements.txt`. Frame-accuracy
   behaviour shifts between ffmpeg builds; a floating version turns a
   reproducible pipeline into a mystery.
6. **Detect, don't ask.** Aspect ratio and letterbox/pillarbox masking are
   detected with `cropdetect` and shown to the user. Never require them to type
   it in — a wrong answer quietly degrades detection.

   *Revised after testing real deliveries:* the mask is **reported, never
   applied**. Two files from the same show returned 1920:922:0:72 and
   1920:920:0:72, because cropdetect's answer depends on picture content; and a
   mini cut can mix masked and unmasked shots, which one global crop cannot
   describe. Output is always full frame — the splitter returns the source's
   own shots, bars and all. Feeding a mask to the detector only is a possible
   refinement, measured against the golden set, not an assumption.

---

## Current scope: hard cuts only

Source material has no editorial transitions — no dissolves, fades, or wipes.
This simplifies things and the simplification is intentional:

- A boundary is a single frame number, not a range. No `transition_in` /
  `transition_out` handling.
- Default thresholds should work without tuning. Hard cuts sit far from the
  decision boundary.

Still expected, and still handled:

- **Flash frames and in-shot camera flashes** — main false-positive source.
  Minimum shot length filter (6–8 frames), merges logged not silently dropped.
- **Speed ramps and whip pans** — main false-negative source.
- Two-pass structure stays even though PySceneDetect alone would likely suffice,
  because the disagreement flag is what makes unattended runs safe, and because
  dissolve support should be an addition rather than a rebuild.

---

## Pipeline

### 1. Probe

- `ffprobe` the source. Capture duration, resolution, codec, `r_frame_rate`,
  `avg_frame_rate`, start timecode.
- Reject VFR sources (`r_frame_rate != avg_frame_rate`) with a clear message.
  Normalizing them is deferred until a real VFR source turns up.
- `cropdetect` for masking. Report findings to the UI.
- Estimate disk requirement and warn before the job, not after the drive fills.
  ProRes 422 at 1080p24 is roughly 1.15 GB/min, and we write mezzanine + splits.

### 2. Detect

- Pass 1: TransNetV2 ONNX. Per-frame transition probability, not a binary.
- Pass 2: PySceneDetect `AdaptiveDetector`.
- Reconcile into a boundary list. Both agree → high confidence. One fires only →
  flag for review. Apply minimum shot length merge.

### 3. Cut

- Transcode source to all-intra mezzanine.
- Split each shot with `-c copy` against the mezzanine.
- Emit JSON sidecar (see below).

One file per shot is the whole output. Stills, thumbnails and contact sheets
belong to the identifier tab.

### 4. Validate

- Assert shot durations sum to total duration, zero gaps, zero overlaps.
- Concat splits back together, frame-hash compare against the mezzanine. Catches
  dropped or duplicated frames.
- Any failure blocks the job and surfaces in the UI. Do not warn-and-continue.

---

## Output format

One JSON sidecar per source job:

```json
{
  "source": { "path": "...", "fps": 25, "start_tc": "10:00:00:00",
              "frame_count": 1500, "resolution": "1920x1080" },
  "environment": { "ffmpeg": "...", "onnxruntime": "...",
                   "model_sha256": "..." },
  "shots": [
    { "index": 1, "start_frame": 0, "end_frame": 74,
      "start_tc": "10:00:00:00", "end_tc": "10:00:02:24",
      "confidence": 0.99, "detectors_agreed": true,
      "file": "shot_001.mov" }
  ],
  "validation": { "passed": true, "checks": { } }
}
```

Recording the resolved environment matters: when a boundary looks wrong months
later, you need to know exactly what produced it.

---

## Golden set

`tests/golden/` holds hand-labelled ground truth — a CSV of true cut frames per
test video.

Its purpose is **not** to validate TransNetV2, whose accuracy on hard cuts is a
known quantity. It validates *our pipeline*: off-by-one errors between detector
output and frame index, frame rate conversion mistakes (23.976 / 29.97), the
cutter landing on the wrong side of a boundary, mezzanine frames dropped or
duplicated. A correct model wired up slightly wrong produces output that looks
fine in a thumbnail and is wrong in every clip.

Score precision/recall with a ±2 frame tolerance. Tune against this, never by
eye. Re-run on every parameter change — it is the regression suite.

---

## Task breakdown

Build in this order. Each should be independently verifiable and separately
committed.

0. **Scaffold + dependency panel** *(done)* — FastAPI server, localhost UI
   shell, path picker, environment checks.
1. **Timecode engine** *(done)* — frame/timecode conversion, drop-frame, exact
   seek times. First because every stage after it depends on this arithmetic
   being right, and it is testable without a single video file.
2. **Probe + preprocess** — ffprobe, VFR handling, cropdetect, disk estimate.
3. **Cutting** — mezzanine, frame-accurate splits, JSON sidecar.
4. **Validation** — integrity assertions and the frame-hash round trip.
5. **Detection** — ONNX export, TransNetV2 inference, PySceneDetect pass,
   reconciliation. *This is the task that will take real debugging; the output
   window handling is the fiddly part.*
6. **Progress UI + job wiring** — SSE progress, shot table, pipeline behind one
   button.

Cutting comes before detection deliberately. With probe done, a hand-typed pair
of frame numbers exercises the mezzanine, the splits, the round-trip check and
the sidecar without the ONNX export existing — so when a boundary later lands a
frame late, the cutter has already been proven on known input and the detector
is the only suspect.

---

## Dependency check panel

Three states, not two. CPU-only is *degraded*, not failed — show an honest time
estimate and allow the user to proceed. Only block on what genuinely cannot run.

Check: ffmpeg + ffprobe on PATH and version; **encoder availability** parsed from
`ffmpeg -encoders` (`prores_ks` / `dnxhd` — many builds omit them and you only
find out mid-job); Python version; `onnxruntime` import and available execution
providers; model weights present and checksum-verified; `scenedetect` import;
output directory writable; free disk space.

Every failure gives a copyable fix command, not an error string. Cache the
result with a manual re-check button.

---

## Frontend conventions

- One `index.html`, one `app.js`, one stylesheet. Keep it editable in a text
  editor with no toolchain.
- File paths are typed/pasted or chosen via a backend directory-listing
  endpoint. Never upload multi-GB media through a form to a server on the same
  machine.
- Long operations stream progress over SSE. Never block the UI on a subprocess.

---

## Code conventions

**Read `D:\_repos\CODE_STYLE.md` first.** It holds the agreed conventions for
every repo and the working practice we follow — architecture first, an ordered
TODO list, one task at a time, tested before the next begins. What follows here
is only what is specific to this project.

The point of all of it is that the author can open any file months later and
follow it without re-reading the whole project. Readability beats cleverness.

**Layout**
- `main.py` at the repo root is the entry point. Everything else lives under
  `src/<package>/`, imported absolutely: `from src.core.models import Shot`.
- Packages group by *role*, not by pipeline order: `core`, `media`, `detection`,
  `validation`, `ui`. A new module goes in the package whose description in
  `src/<package>/__init__.py` already covers it, or the grouping is wrong.
- `src/pipeline.py` holds stage order and nothing else. Logic lives in stages.
- `src/ui/server.py` is the only module that knows about HTTP.
- `src/media/ffmpeg_tools.py` is the only module that runs a subprocess.

**Every module starts with a docstring** giving its Title Case name, what it
does, and — where a decision is not obvious — why it exists at all. The "why"
is the part worth writing; the "what" is usually visible in the code.

**Sections are separated by `# --- CAPS ---` banners.** Group related functions
under one. It should be possible to find a function by skimming banners.

**Data models are Pydantic `BaseModel`**, not dicts and not bare dataclasses.
A model gives the sidecar validation on the way in and on the way out. Fields
carry a short trailing comment when the name does not fully explain them.

**Docstrings** are short, with `Args:` / `Returns:` / `Raises:` when a function
takes more than one argument. `Notes:` is for the trap a future reader would
otherwise fall into.

**Comments explain why, never what.** No comment restating the line below it.
Do comment: an off-by-one that looks wrong but is not, a constant with a
non-obvious origin, an argument order that matters.

**Naming**
- Functions are verb phrases: `build_mezzanine`, `merge_detections`.
- Anything holding a frame number says so: `start_frame`, not `start`.
- No abbreviations beyond the domain's own (`fps`, `tc`, `sha256` are fine).

**Pseudocode before implementation.** New functions land as a signature, a real
docstring, and numbered `# PSEUDOCODE` steps ending in `raise NotImplementedError`.
That is a reviewable plan. The author reads and agrees the plan before it
becomes code.

**Ask before restructuring.** Moving or renaming modules, adding a package, or
changing a settled decision is a conversation first, not a commit.

## Repo conventions

- Commit at task granularity or finer. When an agent-written change breaks
  something, `git diff` against a known-good commit is how it gets found.
- `.gitignore` test media and output directories **before the first commit**.
  Mini cuts and ProRes mezzanines will blow past GitHub's file size limits and
  removing them from history afterwards is genuinely painful.
- Dev happens on Windows; the app must also run on macOS. Keep everything
  path-agnostic (`pathlib`, no hardcoded separators, no shell-specific calls).

---

## Deferred — do not build yet

The splitter detects cuts and writes one file per shot. That is the whole job.

- **Per-shot stills** — QC and identifier input. The shot files are enough to
  check a boundary; stills belong to the identifier tab.
- **VFR normalisation** — VFR is detected and refused, not rewritten.
- **Exact frame counting by decode** — a fallback for containers that lie about
  `nb_frames`. Add it the first time one actually does.
- **Reading sidecars back** — the identifier tab's entry point.
- Identifier tab in any form.
- Dissolve / fade / wipe transition handling.
- Character reference image matching.
- Excel shot list ingestion and fuzzy matching.
- Native packaging of any kind.
