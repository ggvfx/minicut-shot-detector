# Minicut Shot Detector

A local web app that breaks finished video edits ("mini cuts") into their
constituent shots, and — later — names those shots against a supplied shot list.

Two tabs are planned:

1. **Splitter** — load a mini cut, detect shot boundaries, split into individual
   files in an output directory.
2. **Identifier** — load a directory of split shots, describe them, match them
   against a shot list, human-review the matches, rename on approval.

**Current scope is the Splitter only.** Detection is deterministic: the same
input produces byte-identical boundaries on every run.

## Status

🚦 Pre-alpha — repository scaffolding. Nothing is implemented yet.

Build order:

1. Scaffold + dependency panel
2. Probe + preprocess
3. Detection
4. Cutting
5. Validation + progress UI

## How it works

| Stage | What happens |
|---|---|
| Probe | `ffprobe` the source for fps, resolution, start timecode; `cropdetect` for letterbox masking; estimate disk use |
| Detect | TransNetV2 (ONNX Runtime) as primary, PySceneDetect `AdaptiveDetector` as cross-check, reconciled into one boundary list |
| Cut | Transcode once to an all-intra mezzanine, then stream-copy each shot out of it for frame-accurate splits |
| Validate | Durations sum, no gaps or overlaps, and a concat round-trip frame-hash against the mezzanine |

Every job writes a JSON sidecar recording the shots, their frame boundaries and
timecodes, detector agreement, and the resolved tool and model versions that
produced them.

Current scope is hard cuts only — no dissolves, fades or wipes.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe` on `PATH`, with a `prores_ks` or `dnxhd` encoder
  available
- Roughly 1.2 GB per minute of free disk at 1080p25, for mezzanine plus splits

The app checks all of this on launch and reports anything missing with a
copyable fix command. CPU-only inference is supported but slower.

## Stack

Python 3.11 + FastAPI backend, plain HTML/CSS/vanilla JS frontend served on
localhost. No npm, no build step, no native packaging. `ffmpeg` and `ffprobe`
are invoked as subprocesses, never through Python bindings.

Developed on Windows; also targets macOS.

## Licence

MIT — see [LICENSE](LICENSE).
