/*
 * Source Inspection and Analysis.
 *
 * The two steps before review: read the file and say what it is, then build
 * the mezzanine and proxy the player scrubs through.
 *
 * Neither derives anything the server already knows. The suggested output
 * folder and every timecode on screen are computed in Python, where they are
 * tested, and rendered here as given.
 */

import { state } from "./state.js";
import { showProgress } from "./ui.js";
import { closeReview, openReview } from "./player.js";
import { refreshWorkFiles } from "./work.js";

/**
 * Asks the server to probe the chosen source and renders what it found.
 *
 * Quick, and its job is to catch the wrong file, a variable frame rate or a
 * full disk before committing to the long analyse step.
 */
export async function inspectSource() {
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
 * files among them, so the default is a folder of its own.
 *
 * Every source gets its own suggestion, including the second and third of a
 * sitting. This used to return early whenever an output directory existed at
 * all, which meant the folder chosen for the *previous* source silently
 * became the destination for the next one — the shots then landed somewhere
 * the user had not looked at since the job before.
 *
 * A directory the user chose themselves is still left alone, but only for the
 * source they chose it for: a choice belongs to the job it was made for.
 */
function suggestOutputDirectory() {
    if (state.outputChosenFor === state.sourcePath) return;

    // The path itself comes from the server, which builds it with pathlib
    state.outputDir = state.probe.suggested_output_dir;
    document.getElementById("output-dir").value = state.outputDir;
}

// ===== ANALYSE =====

/**
 * Builds the mezzanine and proxy, then opens the review player.
 *
 * This is the slow call. Everything after it — scrubbing, marking, and the
 * split itself — is fast because the encode has already happened.
 */
export async function analyseSource() {
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
        state.boundaries = body.boundaries.map((boundary) => boundary.frame);
        state.uncertain = new Set(
            body.boundaries
                .filter((boundary) => boundary.found_by.length < 2)
                .map((boundary) => boundary.frame)
        );
        openReview();

    } finally {
        button.disabled = false;
        showProgress(false);
        // A mezzanine just appeared for this source, which also means any
        // previous source's is now sitting there unused
        refreshWorkFiles();
    }
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
