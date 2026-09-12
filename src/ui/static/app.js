/*
 * Front End Logic.
 *
 * Plain JavaScript, no framework and no build step — the file you edit is the
 * file the browser runs.
 *
 * Responsibilities:
 * - Load and render the dependency panel
 * - Drive the path picker against the server's browse endpoint
 * - Inspect a source, then analyse it into a mezzanine and a review proxy
 * - Review cuts frame by frame in the proxy, and mark where shots start
 * - Split, and show what was written
 */

// ===== STATE =====

// Everything the UI knows. Kept in one object so it is obvious what exists.
const state = {
    sourcePath: "",
    outputDir: "",
    pickerMode: null,      // "source" | "output" while the dialog is open
    pickerPath: "",        // Directory currently shown in the dialog
    probe: null,           // Last ProbeReport from the server
    prepared: null,        // Last PreparedJob: source, mezzanine and proxy
    boundaries: [],        // Frames on which shots start, frame 0 implied
};

// ===== ENVIRONMENT PANEL =====

/**
 * Fetches the dependency report and renders it.
 * @param {boolean} refresh - True re-runs the checks instead of using the cache.
 */
async function loadEnvironment(refresh = false) {
    const summary = document.getElementById("environment-summary");
    summary.textContent = "Checking…";

    const params = new URLSearchParams();
    if (state.outputDir) params.set("output_dir", state.outputDir);
    if (refresh) params.set("refresh", "true");

    const response = await fetch(`/api/environment?${params}`);
    const report = await response.json();

    renderEnvironment(report);
}

/**
 * Draws the environment report.
 * Three states, not two: "degraded" is a warning the user may proceed past.
 */
function renderEnvironment(report) {
    const summary = document.getElementById("environment-summary");
    const list = document.getElementById("environment-checks");

    const wording = {
        ok: "Ready",
        degraded: "Ready, with limitations",
        blocked: "Cannot run yet",
    };
    summary.textContent = `${wording[report.overall]} — ${report.platform}`;
    summary.className = `summary ${report.overall}`;

    list.innerHTML = "";
    for (const check of report.checks) {
        const row = document.createElement("li");
        row.className = `check ${check.status}`;

        const label = document.createElement("span");
        label.className = "check-label";
        label.textContent = check.label;

        const detail = document.createElement("span");
        detail.className = "check-detail";
        detail.textContent = check.detail;

        row.append(label, detail);

        // Every failure offers a copyable command rather than just an error
        if (check.fix) {
            const fix = document.createElement("code");
            fix.className = "check-fix";
            fix.textContent = check.fix;
            fix.title = "Click to copy";
            fix.addEventListener("click", () => navigator.clipboard.writeText(check.fix));
            row.append(fix);
        }

        list.append(row);
    }
}

// ===== SOURCE INSPECTION =====

/**
 * Asks the server to probe the chosen source and renders what it found.
 *
 * Quick, and its job is to catch the wrong file, a variable frame rate or a
 * full disk before committing to the long analyse step.
 */
async function inspectSource() {
    const status = document.getElementById("inspect-status");
    showProgress(true);

    if (!state.sourcePath) {
        status.textContent = "Choose a source first.";
        return;
    }

    status.textContent = "Inspecting…";

    const response = await fetch("/api/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            source_path: state.sourcePath,
            output_dir: state.outputDir || null,
        }),
    });

    showProgress(false);

    if (!response.ok) {
        const problem = await response.json();
        status.textContent = problem.detail || "Could not read that file.";
        return;
    }

    status.textContent = "";
    closeReview();
    state.probe = await response.json();
    renderProbe(state.probe);
}

/** Draws the probe report. */
function renderProbe(report) {
    const source = report.source;
    const fps = source.fps_numerator / source.fps_denominator;

    // Shown to three decimals only when the rate is not a whole number, so
    // 25 reads as "25" and 23.976 is not rounded away to "24"
    const fpsLabel = Number.isInteger(fps) ? `${fps}` : fps.toFixed(3);
    const rational = `${source.fps_numerator}/${source.fps_denominator}`;

    renderFacts({
        "Resolution": `${source.width} × ${source.height}`,
        "Codec": source.codec,
        "Frame rate": `${fpsLabel} fps (${rational})`,
        "Frames": source.frame_count.toLocaleString(),
        "Duration": report.duration_timecode,
        "Start timecode": source.start_timecode,
        // Reported for information only — shots are always cut at full frame.
        // Skipped entirely on a refused source, so say so rather than claiming
        // "full frame" for something never looked at.
        "Masking": report.can_split
            ? (source.detected_crop
                ? `${source.detected_crop} (letterboxed — not applied)`
                : "none — full frame")
            : "not checked",
        "Disk needed": `${report.estimated_gb.toFixed(1)} GB` +
            (report.free_gb === null ? "" : ` of ${report.free_gb.toFixed(0)} GB free`),
    });

    const verdict = document.getElementById("source-verdict");
    verdict.textContent = report.can_split ? "Ready to split" : "Cannot split";
    verdict.className = `summary ${report.can_split ? "ok" : "blocked"}`;

    const refusal = document.getElementById("source-refusal");
    refusal.hidden = report.can_split;
    refusal.textContent = report.refusal_reason || "";

    const warnings = document.getElementById("source-warnings");
    warnings.innerHTML = "";
    for (const warning of report.warnings) {
        const row = document.createElement("li");
        row.textContent = warning;
        warnings.append(row);
    }

    // The next step only appears once there is something worth analysing
    document.getElementById("job-card").hidden = !report.can_split;
    suggestOutputDirectory();
}

/**
 * Proposes an output directory beside the source, named after it.
 *
 * Writing shots into the folder holding the masters would scatter a dozen
 * files among them, so the default is a folder of its own. Only ever a
 * suggestion: a directory the user has already chosen is left alone.
 */
function suggestOutputDirectory() {
    if (state.outputDir) return;

    const separator = state.sourcePath.includes("\\") ? "\\" : "/";
    const parts = state.sourcePath.split(/[\/]/);
    const name = parts.pop().replace(/\.[^.]+$/, "");

    state.outputDir = [...parts, `${name}_shots`].join(separator);
    document.getElementById("output-dir").value = state.outputDir;
}

// ===== ANALYSE =====

/**
 * Builds the mezzanine and proxy, then opens the review player.
 *
 * This is the slow call. Everything after it — scrubbing, marking, and the
 * split itself — is fast because the encode has already happened.
 */
async function analyseSource() {
    const status = document.getElementById("analyse-status");
    const button = document.getElementById("analyse-button");

    if (!state.sourcePath || !state.outputDir) {
        status.textContent = "Choose a source and an output directory first.";
        return;
    }

    button.disabled = true;
    showProgress(true);
    status.textContent = "Analysing… building the review copy. This can take a few minutes.";

    try {
        const response = await fetch("/api/analyse", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_path: state.sourcePath,
                output_dir: state.outputDir,
            }),
        });

        const body = await response.json();

        if (!response.ok) {
            status.textContent = body.detail || "Could not analyse that file.";
            return;
        }

        status.textContent = "";
        state.prepared = body;
        state.boundaries = [...body.boundaries];
        openReview();

    } finally {
        button.disabled = false;
        showProgress(false);
    }
}

// ===== REVIEW PLAYER =====

/*
 * Frames, not seconds.
 *
 * The proxy is all-intra, so the browser can seek to any frame exactly. The
 * awkward direction is reading back: currentTime after a seek is a float that
 * does not land cleanly on a frame boundary, and at 23.976 rounding it the
 * obvious way drifts.
 *
 * So we seek to the MIDDLE of a frame's duration, where there is most room
 * either side, and read it back the same way. The frame number burned into the
 * proxy is the check: if the readout and the picture disagree, this is wrong.
 */

/** The source's exact rate as a number — the rational itself lives on the server. */
function frameRate() {
    const source = state.prepared.source;
    return source.fps_numerator / source.fps_denominator;
}

/** The moment at which a frame is unambiguously on screen. */
function secondsForFrame(frame) {
    return (frame + 0.5) / frameRate();
}

/** The frame currently on screen. */
function currentFrame() {
    const player = document.getElementById("proxy-player");
    return Math.floor(player.currentTime * frameRate());
}

/** Moves to a frame, clamped to the source. */
function goToFrame(frame) {
    const player = document.getElementById("proxy-player");
    const last = state.prepared.source.frame_count - 1;
    const target = Math.max(0, Math.min(frame, last));

    player.currentTime = secondsForFrame(target);
    renderReadout(target);
}

/** Steps forward or back, pausing first — stepping while playing is meaningless. */
function stepFrames(count) {
    document.getElementById("proxy-player").pause();
    goToFrame(currentFrame() + count);
}

/** Jumps to the nearest marker in a direction, for working cut to cut. */
function goToCut(direction) {
    const frame = currentFrame();
    const markers = [0, ...state.boundaries];
    const candidates = direction > 0
        ? markers.filter((value) => value > frame)
        : markers.filter((value) => value < frame);

    if (candidates.length === 0) return;

    document.getElementById("proxy-player").pause();
    goToFrame(direction > 0 ? Math.min(...candidates) : Math.max(...candidates));
}

/** Opens the review panel on a freshly prepared job. */
function openReview() {
    const player = document.getElementById("proxy-player");
    const source = state.prepared.source;

    // Sized by the video's own shape, so it does not sit in a wide box with
    // black either side of it
    player.style.aspectRatio = `${source.width} / ${source.height}`;
    player.src = `/api/proxy?path=${encodeURIComponent(state.prepared.proxy_path)}`;

    document.getElementById("review").hidden = false;
    document.getElementById("output-card").hidden = false;
    document.getElementById("result-card").hidden = true;

    player.addEventListener("loadeddata", () => goToFrame(0), { once: true });

    renderTimeline();
}

/** Hides the review panel — a different source needs a different proxy. */
function closeReview() {
    document.getElementById("review").hidden = true;
    document.getElementById("output-card").hidden = true;
    document.getElementById("result-card").hidden = true;
    document.getElementById("proxy-player").removeAttribute("src");
    document.getElementById("cut-count").textContent = "";

    state.prepared = null;
    state.boundaries = [];
}

// ===== MARKERS =====

/**
 * Adds a first frame here, or removes the one already here.
 *
 * Frame 0 always starts the first shot, so it is shown but cannot be removed:
 * there is no shot before it for its frames to join.
 */
function toggleMarker() {
    if (!state.prepared) return;

    const frame = currentFrame();
    const hint = document.getElementById("mark-hint");

    if (frame === 0) {
        hint.textContent = "Frame 0 always starts the first shot";
        return;
    }

    if (state.boundaries.includes(frame)) {
        state.boundaries = state.boundaries.filter((value) => value !== frame);
    } else {
        state.boundaries = [...state.boundaries, frame].sort((a, b) => a - b);
    }

    hint.textContent = "Press F, or use the button";
    renderTimeline();
    renderReadout(frame);
}

/**
 * Seeks to wherever the strip was pressed, and follows the pointer if it moves.
 *
 * Stepping frame by frame is precise and useless for crossing a thousand
 * frames, so the strip is also the scrubber: drag to somewhere near a cut, then
 * step onto it exactly.
 */
function scrubTo(event) {
    if (!state.prepared) return;

    const timeline = document.getElementById("timeline");
    const bounds = timeline.getBoundingClientRect();
    const fraction = (event.clientX - bounds.left) / bounds.width;
    const clamped = Math.max(0, Math.min(fraction, 1));

    goToFrame(Math.round(clamped * (state.prepared.source.frame_count - 1)));
}

/** Starts a drag, and keeps scrubbing until the pointer is released. */
function beginScrub(event) {
    if (!state.prepared) return;

    document.getElementById("proxy-player").pause();
    scrubTo(event);

    // Listening on the window means the drag survives leaving the strip, which
    // is what anyone dragging quickly will do
    window.addEventListener("pointermove", scrubTo);
    window.addEventListener("pointerup", endScrub, { once: true });
}

function endScrub() {
    window.removeEventListener("pointermove", scrubTo);
}

/** Moves the playhead to where the player actually is. */
function renderPlayhead(frame) {
    const playhead = document.getElementById("playhead");
    const last = state.prepared.source.frame_count - 1;
    playhead.style.left = `${(frame / last) * 100}%`;
}

/** Draws a tick for every first frame, placed where it falls in the source. */
function renderTimeline() {
    const timeline = document.getElementById("timeline");
    const last = state.prepared.source.frame_count - 1;
    timeline.innerHTML = "";

    // The playhead lives on the strip too, so it is redrawn with the ticks
    const playhead = document.createElement("div");
    playhead.id = "playhead";
    playhead.className = "playhead";
    timeline.append(playhead);

    // Frame 0 is a first frame too, drawn differently because it is fixed
    for (const frame of [0, ...state.boundaries]) {
        const tick = document.createElement("button");
        tick.className = frame === 0 ? "tick fixed" : "tick";
        tick.style.left = `${(frame / last) * 100}%`;
        tick.title = `Frame ${frame}`;
        tick.addEventListener("pointerdown", (event) => {
            event.stopPropagation();
            document.getElementById("proxy-player").pause();
            goToFrame(frame);
        });
        timeline.append(tick);
    }

    const shots = state.boundaries.length + 1;
    document.getElementById("cut-count").textContent = `${shots} shot${shots === 1 ? "" : "s"}`;
}

/** Shows the current frame, and what the mark button would do to it. */
function renderReadout(frame) {
    const last = state.prepared.source.frame_count - 1;
    document.getElementById("frame-readout").textContent = `Frame ${frame} of ${last}`;
    renderPlayhead(frame);

    const marked = frame === 0 || state.boundaries.includes(frame);
    const button = document.getElementById("mark-button");
    button.textContent = marked ? "Remove first frame" : "Mark first frame";
    button.disabled = frame === 0;
}

// ===== SPLITTING =====

/**
 * Sends the marked boundaries to the server and renders the finished job.
 *
 * Quick, because the mezzanine already exists: the shots are stream copies out
 * of it, and only the verification takes any real time.
 */
async function splitSource() {
    const status = document.getElementById("split-status");
    const button = document.getElementById("split-button");

    button.disabled = true;
    showProgress(true);
    status.textContent = "Cutting…";

    try {
        const response = await fetch("/api/split", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_path: state.sourcePath,
                output_dir: state.outputDir,
                boundaries: state.boundaries.map(String),
                full_round_trip: document.getElementById("full-round-trip").checked,
            }),
        });

        const body = await response.json();

        if (!response.ok) {
            status.textContent = body.detail || "The split could not be completed.";
            document.getElementById("result-card").hidden = true;
            return;
        }

        status.textContent = "";
        renderJob(body);

    } finally {
        button.disabled = false;
        showProgress(false);
    }
}

/**
 * Shows or hides the working indicator.
 *
 * It reports that work is happening, not how far along it is. Per-stage
 * progress needs streaming, which is its own task, and a percentage invented
 * here would be a lie told confidently.
 */
function showProgress(running) {
    document.getElementById("progress").hidden = !running;
}

/** Draws the finished job: the verdict, any failures, and every shot written. */
function renderJob(job) {
    document.getElementById("result-card").hidden = false;

    const verdict = document.getElementById("result-verdict");
    verdict.textContent = job.validation.passed
        ? `Verified — ${job.shots.length} shots`
        : "Validation failed";
    verdict.className = `summary ${job.validation.passed ? "ok" : "blocked"}`;

    const failures = document.getElementById("result-failures");
    failures.innerHTML = "";
    for (const failure of job.validation.failures) {
        const row = document.createElement("li");
        row.textContent = failure;
        failures.append(row);
    }

    const body = document.querySelector("#shot-table tbody");
    body.innerHTML = "";

    for (const shot of job.shots) {
        const row = document.createElement("tr");
        const length = shot.end_frame - shot.start_frame + 1;

        for (const value of [
            shot.index,
            `${shot.start_frame} – ${shot.end_frame}`,
            `${length} frames`,
            timecodeFor(shot.start_frame, job.source),
            fileNameOf(shot.file),
        ]) {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.append(cell);
        }

        body.append(row);
    }

    const sidecar = document.getElementById("result-sidecar");
    sidecar.textContent = job.sidecar_path ? `Sidecar: ${fileNameOf(job.sidecar_path)}` : "";
}

/**
 * Frame number as a timecode, for reading against an editor's timeline.
 *
 * Deliberately simple: the server owns the exact arithmetic, including
 * drop-frame, and this is a display convenience over whole frames.
 */
function timecodeFor(frame, source) {
    const labelsPerSecond = Math.ceil(source.fps_numerator / source.fps_denominator);
    const total = frame + startFrames(source.start_timecode, labelsPerSecond);

    const frames = total % labelsPerSecond;
    const seconds = Math.floor(total / labelsPerSecond);

    const pad = (value) => String(value).padStart(2, "0");
    return [
        pad(Math.floor(seconds / 3600) % 24),
        pad(Math.floor(seconds / 60) % 60),
        pad(seconds % 60),
        pad(frames),
    ].join(":");
}

/** The source's start timecode as a frame count. */
function startFrames(timecode, labelsPerSecond) {
    const [hours, minutes, seconds, frames] = timecode.split(/[:;]/).map(Number);
    return ((hours * 60 + minutes) * 60 + seconds) * labelsPerSecond + frames;
}

/** Last path segment, so a full Windows path does not fill the table. */
function fileNameOf(path) {
    return path ? path.split(/[\\/]/).pop() : "";
}

/** Renders a label/value map into the facts list. */
function renderFacts(facts) {
    const list = document.getElementById("source-facts");
    list.innerHTML = "";

    for (const [label, value] of Object.entries(facts)) {
        const term = document.createElement("dt");
        term.textContent = label;

        const definition = document.createElement("dd");
        definition.textContent = value;

        list.append(term, definition);
    }
}

// ===== PATH PICKER =====

/**
 * Opens the picker.
 * @param {string} mode - "source" picks a video file, "output" picks a folder.
 */
async function openPicker(mode) {
    state.pickerMode = mode;
    document.getElementById("picker").showModal();
    await showDirectory("");
}

/**
 * Lists a directory in the picker.
 * @param {string} path - Empty string asks the server for the home folder.
 */
async function showDirectory(path) {
    const params = new URLSearchParams();
    if (path) params.set("path", path);
    if (state.pickerMode === "source") params.set("videos_only", "true");

    const response = await fetch(`/api/browse?${params}`);
    if (!response.ok) return;

    const listing = await response.json();
    state.pickerPath = listing.path;

    document.getElementById("picker-path").textContent = listing.path;
    renderRoots(listing.roots);
    renderEntries(listing);
}

/** Draws the drive letter shortcuts. */
function renderRoots(roots) {
    const container = document.getElementById("picker-roots");
    container.innerHTML = "";

    for (const root of roots) {
        const button = document.createElement("button");
        button.className = "secondary";
        button.textContent = root;
        button.addEventListener("click", () => showDirectory(root));
        container.append(button);
    }
}

/** Draws the directory contents, with a row to step back up. */
function renderEntries(listing) {
    const list = document.getElementById("picker-entries");
    list.innerHTML = "";

    if (listing.parent) {
        const up = document.createElement("li");
        up.className = "entry directory";
        up.textContent = "↑ Up one level";
        up.addEventListener("click", () => showDirectory(listing.parent));
        list.append(up);
    }

    for (const entry of listing.entries) {
        const row = document.createElement("li");
        row.className = `entry ${entry.is_directory ? "directory" : "file"}`;
        row.textContent = entry.name;

        if (entry.is_directory) {
            row.addEventListener("click", () => showDirectory(entry.path));
        } else if (state.pickerMode === "source") {
            row.addEventListener("click", () => choosePath(entry.path));
        }

        list.append(row);
    }
}

/** Accepts a path from the picker and closes it. */
function choosePath(path) {
    if (state.pickerMode === "source") {
        state.sourcePath = path;
        document.getElementById("source-path").value = path;
    } else {
        state.outputDir = path;
        document.getElementById("output-dir").value = path;
        // Free space and writability are checked against the chosen volume
        loadEnvironment(true);
    }

    document.getElementById("picker").close();
}

// ===== KEYBOARD =====

/**
 * Transport shortcuts, so review can be done without leaving the keyboard.
 *
 * Ignored while typing in a field, or the path box could not contain an "f".
 */
function handleKey(event) {
    if (!state.prepared || document.getElementById("review").hidden) return;

    const typing = ["INPUT", "TEXTAREA"].includes(event.target.tagName);
    if (typing) return;

    const step = event.shiftKey ? 10 : 1;
    const actions = {
        ArrowLeft: () => stepFrames(-step),
        ArrowRight: () => stepFrames(step),
        "[": () => goToCut(-1),
        "]": () => goToCut(1),
        f: toggleMarker,
        F: toggleMarker,
        " ": togglePlay,
    };

    const action = actions[event.key];
    if (action) {
        event.preventDefault();
        action();
    }
}

/** Play or pause, and keep the button's label honest. */
function togglePlay() {
    const player = document.getElementById("proxy-player");
    const button = document.getElementById("play-button");

    if (player.paused) {
        player.play();
        button.textContent = "Pause";
    } else {
        player.pause();
        button.textContent = "Play";
    }
}

// ===== WIRING =====

document.addEventListener("DOMContentLoaded", () => {
    loadEnvironment();

    document.getElementById("recheck-button")
        .addEventListener("click", () => loadEnvironment(true));

    for (const button of document.querySelectorAll("[data-picker]")) {
        button.addEventListener("click", () => openPicker(button.dataset.picker));
    }

    document.getElementById("picker-close")
        .addEventListener("click", () => document.getElementById("picker").close());

    // "Choose this folder" applies to the directory currently shown
    document.getElementById("picker-choose")
        .addEventListener("click", () => choosePath(state.pickerPath));

    document.getElementById("inspect-button").addEventListener("click", inspectSource);
    document.getElementById("analyse-button").addEventListener("click", analyseSource);
    document.getElementById("split-button").addEventListener("click", splitSource);

    // Transport
    document.getElementById("play-button").addEventListener("click", togglePlay);
    document.getElementById("step-back").addEventListener("click", (e) => stepFrames(e.shiftKey ? -10 : -1));
    document.getElementById("step-forward").addEventListener("click", (e) => stepFrames(e.shiftKey ? 10 : 1));
    document.getElementById("previous-cut").addEventListener("click", () => goToCut(-1));
    document.getElementById("next-cut").addEventListener("click", () => goToCut(1));
    document.getElementById("mark-button").addEventListener("click", toggleMarker);
    document.getElementById("timeline").addEventListener("pointerdown", beginScrub);

    // The readout follows playback as well as stepping
    document.getElementById("proxy-player")
        .addEventListener("timeupdate", () => {
            if (state.prepared) renderReadout(currentFrame());
        });

    document.addEventListener("keydown", handleKey);

    // Typed paths are as valid as picked ones
    document.getElementById("source-path")
        .addEventListener("change", (event) => { state.sourcePath = event.target.value; });

    document.getElementById("output-dir")
        .addEventListener("change", (event) => {
            state.outputDir = event.target.value;
            loadEnvironment(true);
        });
});
