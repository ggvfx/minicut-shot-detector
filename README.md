# Minicut Shot Detector

**Minicut Shot Detector** is a frame-accurate shot segmentation utility for
finished video edits. It breaks a "mini cut" back into its constituent shots as
individual media files, then — in a later phase — names those shots against a
supplied shot list. Built for VFX and post-production editorial turnovers,
where a delivered cut has to be reversed back into per-shot media without a
single frame landing on the wrong side of a boundary.

## Project Status
🚦 **Project Status:** Pre-Alpha (Source Inspection)
The app shell, dependency panel, path picker and source inspection are working.
Cutting and detection are architected as reviewed skeletons and not yet
implemented.

**Current Capabilities:**
* **Source Inspection:** Reads frame rate as an exact rational, frame count,
  duration, start timecode and codec, and reports what it found before any
  work starts.
* **Masking Detection:** Multi-sample `cropdetect` finds letterbox and
  pillarbox bars, shown for confirmation with a manual override.
* **Variable Frame Rate Refusal:** VFR sources have no stable frame-to-time
  mapping, so they are refused with an explanation rather than cut badly.
* **Disk Estimation:** Estimates the mezzanine and splits against free space
  on the output volume, before the job rather than when the drive fills.
* **Dependency Panel:** Three-state environment reporting (ready / degraded /
  blocked), with a copyable fix command for every failure and a manual re-check.
* **Local Path Picker:** Server-side directory browsing, so multi-gigabyte media
  is never uploaded through the browser.

**Next Milestone:** Frame-accurate cutting — all-intra mezzanine, stream-copy
splits and the round-trip validation that proves them.

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

Requires **Python 3.11+** and **ffmpeg** on `PATH` with either the `prores_ks`
or `dnxhd` encoder. The app checks all of this on launch and tells you how to
fix anything missing.

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

Run the tests with `pytest` from the repo root.

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

### Phase 3: Cutting & Validation (Current)
* All-intra mezzanine and frame-accurate stream-copy splits.
* Integrity and frame-hash round-trip validation.
* JSON sidecar with the full resolved environment.

### Phase 4: Detection
* TransNetV2 ONNX export as a committed build step.
* Sliding-window inference and per-frame transition probabilities.
* PySceneDetect cross-check pass and boundary reconciliation.

### Phase 5: Progress & Orchestration
* SSE progress streaming, shot review table, full pipeline behind one button.

## 🚀 Overview

A delivered mini cut is a single file. Getting back to per-shot media by hand
means scrubbing for cuts, noting timecodes, and trimming clip by clip — slow,
and easy to be a frame out in a way nobody notices until the work is downstream.

The tool follows a **"Deterministic"** and **"Prove It"** philosophy:

1. **Deterministic:** No LLM, no agent, no adaptive thresholds in the detection
   path. Identical input produces byte-identical boundaries on every run.
   Judgment work belongs in the identifier tab, not the splitter.
2. **Prove It:** Every job is validated before it is handed over. The splits are
   joined back together and frame-hash compared against the source, so a dropped
   or duplicated frame fails the job rather than reaching a downstream artist.

## ✨ Key Features

* **Frame-Accurate Splitting:** Transcodes once to an all-intra mezzanine, then
  stream-copies each shot. Cutting a long-GOP source directly snaps silently to
  the nearest keyframe — up to half a second away from the requested frame.
* **Two-Detector Reconciliation:** TransNetV2 runs as the primary pass with
  PySceneDetect as an independent cross-check. Agreement means confidence;
  disagreement flags the boundary for human review, which is what makes an
  unattended run safe to trust.
* **Integer Frames Throughout:** Frame numbers are integers everywhere and
  timecode is derived only at output. Frame rates are held as exact rationals
  (24000/1001), never as rounded floats that drift a frame over a long edit.
* **Round-Trip Verification:** Concatenates the written shots and compares
  per-frame hashes against the mezzanine. Any failure blocks the job — the
  validation stage never warns and continues.
* **Flash-Frame Filtering:** A minimum shot length merges the sub-threshold
  shots that camera flashes produce, and every merge is logged on the shot
  rather than silently applied.
* **Detect, Don't Ask:** Aspect ratio and letterbox masking are found with
  `cropdetect`, sampled across the file, then shown for confirmation with an
  override. A mask typed in wrongly quietly degrades detection.
* **Honest Dependency Reporting:** Three states, not two. CPU-only inference is
  degraded rather than failed — the cost is shown and the user decides.
* **Reproducible Sidecars:** Every job records the resolved ffmpeg build,
  runtime versions and model checksum alongside the shots, so a boundary that
  looks wrong months later can be traced to what produced it.

## 🛠️ Technical Stack
* **Language:** Python 3.11+
* **Backend:** FastAPI, Uvicorn, Pydantic
* **Frontend:** Plain HTML, CSS and vanilla JavaScript — no npm, no build step
* **Detection:** TransNetV2 via ONNX Runtime, PySceneDetect
* **Media Engine:** ffmpeg / ffprobe as subprocesses, never a Python binding

## 📂 Project Structure
* `main.py`: Entry point — starts the local server and opens the UI.
* `src/core/`: Config, data models, timecode maths, ffmpeg toolchain, environment checks.
* `src/media/`: Source probing, mezzanine creation and shot extraction.
* `src/detection/`: TransNetV2, PySceneDetect cross-check and boundary reconciliation.
* `src/validation/`: Integrity and round-trip checks that can block a job.
* `src/ui/`: FastAPI routes, path picker and the browser front end.
* `scripts/`: One-off build steps, including the TransNetV2 ONNX export.
* `tests/`: Unit tests and the hand-labelled golden set.

## Licence
MIT — see [LICENSE](LICENSE).
