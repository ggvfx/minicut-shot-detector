# TODO

Working reference. The current phase is broken into tasks; later phases are
listed only by what they are, and get broken down when we reach them.

Scope reminder: **the splitter detects cuts and writes one file per shot.**
That is the whole job. Anything else is in `Deferred` at the bottom.

---

## Phase 1 — Scaffold & Foundations ✅ Complete

- [x] FastAPI server on localhost, no-build-step front end
- [x] Dependency panel: three states, copyable fixes, cached with re-check
- [x] Encoder verification parsed from `ffmpeg -encoders`
- [x] Server-side path picker for source and output
- [x] `MediaToolchain` — the only place a subprocess runs
- [x] `Timecode` engine — exact rationals, drop-frame, ffmpeg seek strings *(62 tests)*
- [x] Scope trim: stills, VFR normalisation, decode frame counting, sidecar reading

---

## Phase 2 — Probe & Preprocess ⬅ Current

Everything below is `SourceProbe` in `src/media/probe.py`, plus the UI to show
what it found.

- [ ] **2.1 `probe()`** — ffprobe JSON to `SourceInfo`
  - Exact rational frame rate, kept as numerator/denominator
  - Width, height, codec, frame count, start timecode
  - Test against a generated fixture clip, not a real mini cut
- [ ] **2.2 VFR detection** — compare `r_frame_rate` with `avg_frame_rate`,
  set the flag, and refuse the job with a clear message
- [ ] **2.3 `detect_crop()`** — multi-sample `cropdetect`, most common result
  wins, `None` when the frame is already full
- [ ] **2.4 `estimate_disk_required()`** — mezzanine plus splits, scaled by
  resolution, compared against free space
- [ ] **2.5 `POST /api/probe`** — route returning source info, crop and estimate
- [ ] **2.6 UI panel** — show what was found, with a crop override field
- [ ] **2.7 Test fixtures** — a script that generates short test clips with
  ffmpeg (25, 23.976, 29.97) so tests never depend on real media

**Done when:** pointing the app at a real file shows its frame rate, timecode,
detected crop and disk estimate, and a VFR file is refused with a clear reason.

---

## Phase 3 — Cutting & Validation

Mezzanine, frame-accurate splits, integrity checks, round-trip frame hashing,
JSON sidecar. Proven with hand-typed frame numbers before any detector exists.

## Phase 4 — Detection

TransNetV2 ONNX export, sliding-window inference, PySceneDetect cross-check,
boundary reconciliation and the minimum shot length filter.

## Phase 5 — Progress & Orchestration

SSE progress streaming, the shot review table, and the whole pipeline behind
one button.

---

## Deferred — do not build

Each of these was cut deliberately. The reason is recorded so it reads as a
decision rather than an oversight.

- **Per-shot stills** — identifier tab input; the shot files are enough to
  check a boundary
- **VFR normalisation** — VFR is refused, not rewritten; wait for a real one
- **Exact frame counting by decode** — a fallback for containers that lie about
  `nb_frames`; add it the first time one does
- **Reading sidecars back** — the identifier tab's entry point
- **Progress callbacks** — plumbing added in Phase 5, not before
- Identifier tab in any form
- Dissolve / fade / wipe handling
- Excel shot list ingestion, character reference matching, native packaging
