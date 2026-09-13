/*
 * Splitting, and the Job It Produced.
 *
 * Sends the marked boundaries to the server and renders what came back. Quick,
 * because the mezzanine already exists: the shots are stream copies out of it.
 */

import { state } from "./state.js";
import { fileNameOf, showProgress } from "./ui.js";
import { refreshWorkFiles } from "./work.js";

/**
 * Sends the marked boundaries to the server and renders the finished job.
 *
 * Quick, because the mezzanine already exists: the shots are stream copies out
 * of it, and only the verification takes any real time.
 */
export async function splitSource() {
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
                // The default pixel check. Full round-trip verification is
                // supported by the API but no longer offered on the page —
                // see the note in index.html.
                full_round_trip: false,
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
        // A job that passed cleans up after itself; one that failed keeps its
        // mezzanine deliberately, and this is what says so
        refreshWorkFiles();
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
            shot.start_timecode,
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
