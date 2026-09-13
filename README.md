# Minicut Shot Detector

**Minicut Shot Detector** breaks a generative AI "mini cut" back into its
constituent shots as individual, frame-accurate media files — and, in a later
phase, names those shots against a supplied shot list so they can be tracked
like any other shot in the pipeline.

Models such as Seedance can now return a *sequence* rather than a shot: several
cuts arriving as one clip. Production tracks work per shot, so that clip has to
be split, named and registered before anyone can schedule, review or version
what is in it. This automates the splitting and naming half.

## Project Status
🚦 **Project Status:** Splitter complete · Identifier designed, not built
The splitter works end to end: point it at a mini cut, let it find the shots,
correct anything it got wrong, and get back one verified file per shot with a
JSON sidecar.

The identifier — naming those shots against a production's shot list — is fully
designed and skeletoned, and is what v1 waits on. See
[ARCHITECTURE.md](ARCHITECTURE.md#the-identifier) for the shape and
[TODO.md](TODO.md) for the order it gets built in.

**Current Capabilities:**
* **Automatic Shot Detection:** Two PySceneDetect passes — ContentDetector and
  AdaptiveDetector — run over the mezzanine and their results are merged. Each
  boundary records which detectors found it, so one found by a single pass is
  flagged for a look while agreement passes quietly.
* **Frame-Accurate Review:** Plays a small all-intra proxy with each frame's
  number burned in, so the player's frame and the picture's frame can be
  checked against each other. Step a frame at a time, jump shot to shot, and a
  green dot beside the burned-in number marks a first frame while scrubbing.
  Detected marks can be removed and missed ones added by hand.
* **Splitting:** Cuts a mini cut into one file per shot with audio carried
  through, verifies every cut landed on the frame asked for, and writes a JSON
  sidecar recording what produced it.
* **Source Inspection:** Reads frame rate as an exact rational, frame count,
  duration, start timecode and codec, and reports what it found before any
  work starts.
* **Masking Detection:** Multi-sample `cropdetect` finds letterbox and
  pillarbox bars and reports them. Shots are always cut at full frame.
* **Variable Frame Rate Refusal:** VFR sources have no stable frame-to-time
  mapping, so they are refused with an explanation rather than cut badly.
* **Disk Estimation:** Estimates the mezzanine and splits against free space
  on the output volume, before the job rather than when the drive fills.
* **Dependency Panel:** Three-state environment reporting (ready / degraded /
  blocked) covering only what a job actually needs — Python, ffmpeg, ffprobe,
  the mezzanine encoders, PySceneDetect and free space — with a copyable fix
  command for every failure and a manual re-check. Every row is something the
  user can act on when they read it.
* **Local Path Picker:** Server-side directory browsing, so multi-gigabyte media
  is never uploaded through the browser.
* **Reclaimable Working Files:** A source that is analysed and never split keeps
  its mezzanine, which is about a gigabyte per few minutes. The output panel
  reports what that is holding and clears it on request — never automatically,
  and never the source currently open.

**The splitter is functionally complete.** Point it at a mini cut, let it find
the shots, correct anything it got wrong, and get back one file per shot.

Detection was judged on a mix of CG renders and AI generations and kept as it
is: the classical passes get the cuts, fast cuts are where they trip, and
correcting those by hand takes seconds. A neural pass (TransNetV2 via ONNX
Runtime) was designed, skeletoned and then **removed** rather than left in the
tree — see [TODO.md](TODO.md) for the reasoning. What would justify reviving it
is gradual transitions, which a frame-to-frame difference cannot see.

**Next Milestone:** Progress reporting. Analyse and split currently run with no
feedback beyond a disabled button.

## Development Approach

This project is developed with an AI coding assistant (Claude Code) under a
deliberate process rather than an open-ended one:

* **Architecture first.** Data flow, module boundaries and settled technical
  decisions were agreed in writing before implementation began — see
  [ARCHITECTURE.md](ARCHITECTURE.md) and [CLAUDE.md](CLAUDE.md).
* **Skeletons before code.** Modules land first as signatures, docstrings and
  pseudocode, reviewed and approved before they are implemented.
* **One task at a time.** Each stage is built, tested and reviewed before the
  next begins, and committed separately so any change can be traced.
* **Reviewed and understood.** I read every module. Anything I cannot follow
  gets rewritten or explained, not merged.

The engineering decisions here are mine; the assistant works to them.

## Install & Run

Requires **Python 3.11+** and **ffmpeg** on `PATH`, built with `libx264` (and
`libx265` for h265 sources). The app checks all of this on launch and tells you
how to fix anything missing.

```bash
# 1. Clone and enter the repo
git clone https://github.com/ggvfx/minicut-shot-detector.git
cd minicut-shot-detector

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Run — opens http://127.0.0.1:8765 in your browser
python main.py
```

If ffmpeg is missing: `winget install Gyan.FFmpeg` on Windows,
`brew install ffmpeg` on macOS.

Run the tests with `pytest` and the linter with `ruff check .`, both from
the repo root.

## Using it

1. **Choose a source.** Type the path or browse for it; nothing is uploaded,
   since the media and the app are on one machine.
2. **Inspect source.** Quick. Confirms the file is what you think it is, and
   refuses anything that cannot be cut accurately before you wait on it.
3. **Analyse for cuts.** The slow step: the all-intra mezzanine and the review
   proxy are built here, once.
4. **Review.** Play through, step with `←` and `→` (hold Shift for ten), jump
   between shots with `[` and `]`, and press `F` to mark or unmark the frame a
   shot starts on. Drag the timeline to move about quickly.
5. **Split into shots.** The output directory defaults to a folder beside the
   source, named after it. Splitting is fast, because the encode already
   happened. Every cut is verified against the source before the job is called
   done, and a JSON sidecar records what produced it.

Working files — the mezzanine and the review copy — live in a `.minicut-work`
folder inside the output directory and are removed when a job passes. A job
that fails keeps them, so there is something to investigate with.

The number burned into the corner of the proxy is the frame you are on. If it
ever disagrees with the readout, stop and say so — that is the one thing in
here that must never drift.

## Strategic Roadmap

### Phase 1: Scaffold & Foundations (Complete)
* FastAPI server on localhost with a no-build-step front end.
* Three-state environment checks with copyable fixes and result caching.
* Server-side path picker for source and output selection.
* SMPTE timecode engine — exact rational frame rates, drop-frame handling and
  frame-accurate seek times, covered by 62 unit tests.

### Phase 2: Probe & Preprocess (Complete)
* `ffprobe` metadata, exact rational frame rates, and source start timecode.
* Variable frame rate detection, reported and refused rather than rewritten.
* Multi-sample `cropdetect` masking with UI confirmation and override.
* Disk requirement estimation before a job starts.

### Phase 3: Cutting & Validation (Complete)
* All-intra mezzanine in the source's own codec, and frame-accurate stream-copy
  splits out of it.
* Integrity and frame-hash round-trip validation.
* JSON sidecar with the full resolved environment.

### Phase 3.5: Review Player (Complete)
* 640px all-intra proxy with burned-in frame numbers, built from the mezzanine.
* Frame stepping, cut-to-cut jumps, a scrubbable timeline, and one key to mark
  or unmark where a shot starts.

### Phase 4: Detection (Complete)
* PySceneDetect ContentDetector and AdaptiveDetector passes.
* Boundary reconciliation, with the detectors that found each cut recorded, so
  the timeline can flag the ones worth a second look.
* Judged on real CG renders and AI generations — good enough, so the planned
  neural pass was cut. The phase finished in three tasks instead of eight
  because the cheap approach was built and tested first.

### Phase 5: Loose Ends (Complete)
* Reclaiming the working files an abandoned analysis leaves behind.
* The front end's own arithmetic moved to Python, where the tests are, and what
  remained split into ES modules.
* Progress streaming was measured and dropped for the splitter: the worst
  realistic source analyses in 44 seconds.

### Phase 6: Two Tabs (Current)
* `src/splitter/` and `src/identifier/` over shared `core/` and `media/`.
* Backend adapters — CLI, HTTP API, local runtime — behind one interface.

### Phase 7: The Identifier
* Observe with a vision model, interpret against the project's own markdown
  files, match attribute by attribute with a confidence derived from which
  attributes agree.
* Rename on approval, reversibly — or export a breakdown with thumbnails to
  seed a database from a blockout.
* Progress comes back here: a batch is 1–40 shots at model speed, which is a
  different measurement from the splitter's 44 seconds.

## 🚀 Overview

An artist generates a mini cut in minutes. Getting it into a production
pipeline takes considerably longer: scrubbing for every cut, noting timecodes,
trimming clip by clip, then naming and registering each one. It is slow, it is
nobody's favourite task, and it is easy to land a frame out in a way nobody
notices until the work is downstream.

The real cost is what never makes it through at all. Material sits inside a
mini cut, gets seen once, and never becomes a shot anyone can find again —
until a director remembers something they saw and nobody can place it. A
sequence that was never split is a sequence the pipeline cannot track.

Nothing here is specific to generative material: the same job comes up whenever
a delivered edit has to be reversed back into per-shot media. That is simply
not the problem that prompted it.

The tool follows a **"Deterministic"** and **"Prove It"** philosophy:

1. **Deterministic:** No LLM, no agent, no adaptive thresholds in the detection
   path. Identical input produces byte-identical boundaries on every run.
   Judgment work belongs in the identifier tab, not the splitter.
2. **Prove It:** Every job is validated before it is handed over. The splits are
   joined back together and frame-hash compared against the source, so a dropped
   or duplicated frame fails the job rather than reaching a downstream artist.

Cutting an h264 or h265 source on an arbitrary frame costs one re-encode
generation — a file can only start on a keyframe, so stream-copying the original
data could only cut where keyframes already are. The mezzanine is therefore
all-intra in the source's own codec at a visually transparent setting, and every
shot is a lossless stream copy out of it.

## ✨ Key Features

* **Review Before You Cut:** The mezzanine is built first, so scrubbing and
  adjusting cost nothing and the split afterwards is a stream copy. Marks are
  placed against a numbered proxy rather than the source, because browsers seek
  long-GOP video approximately and h265 playback depends on the viewer's
  hardware.
* **Frame-Accurate Splitting:** Re-encodes once to an all-intra mezzanine, then
  stream-copies each shot out of it. Cutting a long-GOP source directly snaps
  silently to the nearest keyframe — often seconds from the requested frame.
* **Format Preserved:** Shots come back in the codec and container they went in
  as — h264 in, h264 out; h265 in, h265 out, at the source's resolution, frame
  rate and bit depth. Converting to a delivery format is not this tool's job.
* **Two-Detector Reconciliation:** PySceneDetect's ContentDetector and
  AdaptiveDetector both run, and their boundaries are merged rather than
  intersected. Measured on real deliveries they fail in opposite directions —
  Content finds cuts Adaptive misses in high-motion footage, Adaptive finds
  cuts Content misses in previz — so the union is what gets used. Agreement
  means confidence; a boundary only one pass found is kept and flagged for a
  human glance.
* **Integer Frames Throughout:** Frame numbers are integers everywhere and
  timecode is derived only at output. Frame rates are held as exact rationals
  (24000/1001), never as rounded floats that drift a frame over a long edit.
* **Pixel-Level Verification:** Frame-hashes the first and last frame of every
  shot against the mezzanine, so a shot cut from the wrong place cannot pass a
  frame count. Any failure blocks the job; the validation stage never warns and
  continues. A full round trip — rejoin everything and compare every frame — is
  implemented and tested, but not offered in the UI: boundary hashes catch the
  same class of error for a fraction of the write.
* **Detect, Don't Ask:** Aspect ratio and letterbox masking are found with
  `cropdetect`, sampled across the file, then shown for confirmation with an
  override. A mask typed in wrongly quietly degrades detection.
* **Honest Dependency Reporting:** Three states, not two, and every blocked
  check carries the command that fixes it. The panel reports what a job needs
  and what the user can act on — not what a later version might want, and not
  a choice they have not reached yet.
* **Reproducible Sidecars:** Every job records the resolved ffmpeg build and
  runtime versions alongside the shots, so a boundary that looks wrong months
  later can be traced to what produced it.

## 🛠️ Technical Stack
* **Language:** Python 3.11+
* **Backend:** FastAPI, Uvicorn, Pydantic
* **Frontend:** Plain HTML, CSS and vanilla JavaScript in ES modules the
  browser loads natively — no npm, no bundler, no build step. The front end
  owns no arithmetic: timecodes and paths are computed in Python, where the
  tests are, and rendered as given.
* **Detection:** PySceneDetect (ContentDetector + AdaptiveDetector)
* **Media Engine:** ffmpeg / ffprobe as subprocesses, never a Python binding
* **Mezzanine:** All-intra libx264 / libx265 at CRF 12, matching the source codec
* **Model backends (identifier, designed):** a configured CLI, an HTTP API, or a
  local runtime, behind one interface. The CLI and API paths are the product;
  local inference is an option and never a requirement, because this is built to
  be handed to people whose machines are nothing like the one it was written on.

## 📂 Project Structure

Two features over shared foundations, so where a thing belongs has an answer:

* `main.py`: Entry point — starts the local server and opens the UI.
* `src/core/`: Config, data models, timecode maths, ffmpeg toolchain, environment checks.
* `src/media/`: Source probing, frame sampling, mezzanine, review proxy, extraction.
* `src/splitter/`: Detection, reconciliation, validation, and the splitter pipeline.
* `src/identifier/`: Observation, interpretation, matching, renaming, export *(skeleton)*.
* `src/backends/`: The model adapters — CLI, HTTP API, local runtime *(skeleton)*.
* `src/ui/`: FastAPI routes, path picker and the browser front end.
* `tests/`: Unit and route tests. Test media is generated by ffmpeg in
  `conftest.py`, so no video is ever committed.

## Licence
MIT — see [LICENSE](LICENSE).
