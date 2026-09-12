/*
 * Front End Logic.
 *
 * Plain JavaScript, no framework and no build step — the file you edit is the
 * file the browser runs.
 *
 * Responsibilities:
 * - Load and render the dependency panel
 * - Drive the path picker against the server's browse endpoint
 * - Hold the chosen paths until a job can be started (task 2 onwards)
 */

// ===== STATE =====

// Everything the UI knows. Kept in one object so it is obvious what exists.
const state = {
    sourcePath: "",
    outputDir: "",
    pickerMode: null,      // "source" | "output" while the dialog is open
    pickerPath: "",        // Directory currently shown in the dialog
    probe: null,           // Last ProbeReport from the server
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
 * Takes a moment on a long file — cropdetect samples several points.
 */
async function inspectSource() {
    const status = document.getElementById("inspect-status");

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

    if (!response.ok) {
        const problem = await response.json();
        status.textContent = problem.detail || "Could not read that file.";
        document.getElementById("source-card").hidden = true;
        return;
    }

    status.textContent = "";
    document.getElementById("result-card").hidden = true;
    state.probe = await response.json();
    renderProbe(state.probe);
}

/** Draws the probe report. */
function renderProbe(report) {
    const card = document.getElementById("source-card");
    card.hidden = false;

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

    showJobPanel(report.can_split);
}

// ===== SPLITTING =====

/**
 * Sends the typed boundaries to the server and renders the finished job.
 *
 * Blocking: a long source takes minutes and there is no progress feed yet, so
 * the button says what it is doing and stays disabled until it is done.
 */
async function splitSource() {
    const status = document.getElementById("split-status");
    const button = document.getElementById("split-button");

    if (!state.outputDir) {
        status.textContent = "Choose an output directory first.";
        return;
    }

    const boundaries = document.getElementById("boundaries").value
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0);

    button.disabled = true;
    status.textContent = "Splitting… this can take a few minutes, and the page will wait.";

    try {
        const response = await fetch("/api/split", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source_path: state.sourcePath,
                output_dir: state.outputDir,
                boundaries: boundaries,
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
    }
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
    sidecar.textContent = job.sidecar_path
        ? `Sidecar: ${fileNameOf(job.sidecar_path)}`
        : "";
}

/** The cuts panel is only useful once a source is known to be splittable. */
function showJobPanel(canSplit) {
    document.getElementById("job-card").hidden = !canSplit;
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

    document.getElementById("inspect-button")
        .addEventListener("click", inspectSource);

    document.getElementById("split-button")
        .addEventListener("click", splitSource);

    // Typed paths are as valid as picked ones
    document.getElementById("source-path")
        .addEventListener("change", (event) => { state.sourcePath = event.target.value; });

    document.getElementById("output-dir")
        .addEventListener("change", (event) => {
            state.outputDir = event.target.value;
            loadEnvironment(true);
        });
});
