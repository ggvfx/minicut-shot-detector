# Shot Splitter & Identifier

A local web app for breaking down "mini cuts" into their constituent shots and
naming those shots against a supplied shot list.

The trigger is generative AI: models such as Seedance return a multi-shot
sequence as a single clip, and production tracks work per shot, so those clips
have to be split, named and registered before anything in them can be
scheduled, reviewed or versioned. Doing it by hand is slow enough that material
gets seen once and never enters the pipeline at all. Traditional editorial
turnovers are the same job, and work here too.

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
| Backend | Python 3.11+, FastAPI | SSE for progress streaming, from Phase 5 |
| Frontend | Plain HTML + CSS + vanilla JS | No React, no npm, no build step |
| Serving | FastAPI static files on localhost | User opens in their own browser |
| Detection | PySceneDetect, two passes | `ContentDetector` and `AdaptiveDetector` |
| ~~Detection (neural)~~ | ~~TransNetV2 via ONNX Runtime~~ | **Removed.** Judged unnecessary at 4.3 — see below |
| Media | ffmpeg / ffprobe as subprocesses | Never a Python binding |
| Review | 640px all-intra h264 proxy | Frame numbers burned in |
| Mezzanine | All-intra in the source's own codec | libx264 / libx265, CRF 12 |

### Why there is no neural pass

TransNetV2 was the original plan, designed in detail and written as a skeleton.
It was **removed at 4.3**, when the two PySceneDetect passes were judged on a
mix of CG renders and AI generations and turned out to be good enough: they get
the cuts, fast cuts are where they trip, and fixing those with the manual
first-frame marker is quick.

Removed rather than left in place, because ~300 lines nothing calls is exactly
the bloat this project is trying not to accumulate. Git history holds the
skeleton, TODO.md holds the reasoning.

**Do not reintroduce it speculatively.** The one thing that would justify it is
gradual transitions — dissolves, fades and wipes — which a frame-to-frame
difference cannot see. If that day comes: ONNX, not PyTorch, exported once as a
build step and committed, to avoid a several-hundred-MB torch dependency at
runtime and to get CoreML acceleration on Apple Silicon.

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
   silently move boundaries by up to a GOP length. Re-encode the source once to
   an all-intra mezzanine, then stream-copy each split out of that.

   *Revised after testing real deliveries:* the mezzanine is **all-intra in the
   source's own codec** — h264 in, h264 out; h265 in, h265 out — not ProRes or
   DNxHR. Shots come back in the format they went in as; converting to a
   delivery codec is beyond this tool. Measured on a 1080p24 h264 source:
   all-intra h264 at CRF 12 is 0.21 GB/min against ProRes 422 HQ's 0.87.

   This costs **one re-encode generation**, which is unavoidable. In h264 and
   h265 most frames are defined relative to their neighbours, so a file can
   only start on a keyframe: stream-copying the original data can only cut
   where keyframes already are. Verified by hand — cutting 30 frames out of an
   all-intra mezzanine yields exactly 30 frames, pixel-identical to the source
   span. "Smart cutting" (stream-copy the aligned middle, re-encode only the
   partial groups at each end) is the only way to avoid that generation, and is
   deliberately out of scope.
3. **Review happens against a proxy, never the source.** Browsers seek
   long-GOP h264 and h265 approximately — landing near a frame rather than on
   it — and Chrome plays h265 only where the hardware allows. The proxy is
   all-intra h264 at 640px, built from the mezzanine, so seeking is exact and
   it plays anywhere.

   **Every frame carries its own number, burned in.** The one real risk in a
   frame-accurate player is the readout drifting from the picture, and this
   turns that from something to trust into something to see. Do not remove it
   without replacing the check it provides.

   **The mezzanine is built before review, not after.** It has to exist either
   way and it is the slow part of a job, so building it first makes scrubbing
   free and leaves the split as stream copies. `run()` reuses one that already
   matches its source, so preparing and then cutting encodes the file once.

4. **Working files live in `.minicut-work/` inside the output directory.**
   The mezzanine, the review proxy and the round trip's scratch all go there,
   never beside the shots. An analysis someone walks away from then leaves one
   folder that is obviously not a deliverable, rather than two large files
   sitting among the output. A job that passes deletes the folder; a job that
   fails keeps it, which is when the intermediates are worth having.

5. **Shots tile the source.** There is one kind of marker — the frame a shot
   starts on — and every frame belongs to exactly one shot. Marking frame N
   ends the previous shot at N-1. Frame 0 is always the first shot's first
   frame and cannot be unmarked.

   This was chosen over independent first/last markers, which would let a user
   leave material in no shot at all. That is a legitimate thing to want and it
   would weaken validation from "the shots account for every frame" to "no shot
   overlaps another" — so it is a deliberate decision, not an oversight.

6. **The validation stage ships with v1.** It is not a later addition. See below.

   *Revised after measuring:* there are two pixel checks, not one. The default
   compares the first and last frame of every shot against the mezzanine; the
   full round trip rejoins every shot and compares every frame.

   Both catch what a stream copy can actually get wrong — a shot starting or
   ending a frame out, a file holding the wrong content, a shot missing — because
   the pixels inside a stream-copied shot cannot change. Measured on a 3.4 minute
   mini cut of 17 shots the round trip took roughly six times as long and wrote
   a second copy of the mezzanine while it ran, to catch the same class of error.

   *Revised again:* the round trip is no longer offered in the UI. The code and
   its tests stay, and `POST /api/split` still takes `full_round_trip`, so it is
   a front-end change to bring back if a real failure ever justifies it.
7. **The splitter is deterministic.** Identical input must produce identical
   boundaries on every run, and no judgment enters the detection path — no LLM,
   no agent, nothing that could answer differently twice.

   *Reworded:* this rule used to say "no adaptive thresholds", which
   `AdaptiveDetector` plainly is — it compares each frame against a rolling
   average of its neighbours rather than a constant. It is still deterministic,
   which is what the rule was protecting. The old wording banned a technique;
   this one states the property.
8. **Pinned dependencies.** Exact versions in `requirements.txt`. Frame-accuracy
   behaviour shifts between ffmpeg builds; a floating version turns a
   reproducible pipeline into a mystery.
9. **Detect, don't ask.** Aspect ratio and letterbox/pillarbox masking are
   detected with `cropdetect` and shown to the user. Never require them to type
   it in — a wrong answer quietly degrades detection.

   *Revised after testing real deliveries:* the mask is **reported, never
   applied**. Two files from the same show returned 1920:922:0:72 and
   1920:920:0:72, because cropdetect's answer depends on picture content; and a
   mini cut can mix masked and unmasked shots, which one global crop cannot
   describe. Output is always full frame — the splitter returns the source's
   own shots, bars and all. Feeding a mask to the detector only is a possible
   refinement, and would have to be measured before being believed, not
   assumed.

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
  All-intra h264 at 1080p24 is roughly 0.21 GB/min, and we write mezzanine + splits.

### 2. Prepare

- Re-encode source to an all-intra mezzanine in its own codec.
- Build the 640px review proxy from the mezzanine, frame numbers burned in.

Both happen before anything is cut, so the review that follows costs nothing
and the cutting afterwards is stream copies.

### 3. Detect

- Pass 1: PySceneDetect `ContentDetector` — a fixed threshold.
- Pass 2: PySceneDetect `AdaptiveDetector` — a rolling baseline.
- Reconcile into a boundary list, matching within two frames. Both agree → high
  confidence. One fires only → kept and flagged for review, because measuring
  the two showed each finding real cuts the other missed.
- There is no third pass. A neural one was planned and removed at 4.3.

### 4. Review

- The boundaries appear as markers on the proxy's timeline. A person scrubs,
  steps frame by frame, and marks or unmarks where shots start.
- Detection fills these markers; it does not replace them. The human has the
  last word before anything is written, and a typed list is not asked for.

### 5. Cut

- Split each shot with `-c copy` against the mezzanine.
- Emit JSON sidecar (see below).

One file per shot is the whole output. Stills, thumbnails and contact sheets
belong to the identifier tab.

### 6. Validate

- Assert shot durations sum to total duration, zero gaps, zero overlaps.
- Frame-hash the first and last frame of every shot against the mezzanine. This
  is the default: every failure a stream copy can produce moves a boundary frame.
- Optionally concat the splits back together and frame-hash the whole thing.
  It decodes the job twice and needs room for a second mezzanine, so it is a
  checkbox rather than the default.

  Any timing quoted here is from one machine and one source; keep measurements
  in this file, where the context is stated, and out of the UI.
- The mezzanine is deleted when a job passes and kept when it fails, because a
  failure is when the intermediate is worth having.
- Any failure blocks the job and surfaces in the UI. Do not warn-and-continue.

---

## Output format

One JSON sidecar per source job:

```json
{
  "source": { "path": "...", "fps": 25, "start_tc": "10:00:00:00",
              "frame_count": 1500, "resolution": "1920x1080" },
  "environment": { "ffmpeg": "...", "ffprobe": "...", "scenedetect": "...",
                   "platform": "...", "app": "..." },
  "shots": [
    { "index": 1, "start_frame": 0, "end_frame": 74,
      "start_tc": "10:00:00:00", "end_tc": "10:00:02:24",
      "confidence": 0.99, "detectors_agreed": true,
      "file": "shot_001.mp4" }
  ],
  "validation": { "passed": true, "checks": { } }
}
```

Recording the resolved environment matters: when a boundary looks wrong months
later, you need to know exactly what produced it.

---

## How correctness is proven

There is no golden set. It was planned, and closed at 4.3 along with the neural
pass it existed to justify — scoring precision and recall only matters when you
are choosing between detectors.

What it was *originally* for — off-by-one errors between detector output and
frame index, frame rate conversion mistakes at 23.976 and 29.97, the cutter
landing on the wrong side of a boundary, mezzanine frames dropped or duplicated
— is covered by things that run on every commit instead:

- the timecode suite, on exact rationals and drop-frame
- the frame count asserted on every shot as it is written
- the frames either side of every cut, hashed against the mezzanine
- integrity arithmetic: the shots tile the source, no gaps, no overlaps

That last group is the point. **A detector wired up slightly wrong produces
output that looks fine in a thumbnail and is wrong in every clip** — so the
checks are on the pixels and the arithmetic, not on a score.

If a neural pass is ever revived, a golden set comes back with it, because
choosing between two detectors by eye is tuning by eye.

---

## Task breakdown

**[TODO.md](TODO.md) is the task list.** It holds the current phase broken into
tasks, what is done, and every cut that was made deliberately. Keeping a second
copy here would only let the two disagree.

The ordering principle, which is worth keeping in mind when adding to it:
**cutting was built before detection, on purpose.** A hand-placed pair of frame
numbers exercised the mezzanine, the splits, the verification and the sidecar
without any detector existing — so when a boundary later lands a frame late,
the cutter has already been proven on numbers we chose, and the detector is the
only suspect.

That ordering paid for itself: detection landed in three tasks rather than
eight, and the phase closed early because the cheap approach was tried first.

---

## Dependency check panel

Three states, not two. Only block on what genuinely cannot run.

The panel reports what a job needs, and nothing else. Six checks: Python
version; ffmpeg and ffprobe on PATH and version; **encoder availability**
parsed from `ffmpeg -encoders` (`libx264` required, `libx265` needed for h265
sources — a missing encoder otherwise only surfaces mid-job); `scenedetect`
import; free disk space.

**Every check must be about something the user can act on when they read it.**
One check is written and deliberately not run:

- `check_output_dir` — the directory is chosen at the *end* of the workflow, so
  on launch this only ever said "not chosen yet" and dragged the panel to
  degraded: it announced a fault before the user had done anything, and could
  not be cleared until they had finished. `POST /api/split` refuses a job
  without a directory and the pipeline creates one that does not exist, so
  nothing is lost.

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
  Mini cuts and all-intra mezzanines will blow past GitHub's file size limits and
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
