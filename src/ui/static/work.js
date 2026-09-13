/*
 * Working Files.
 *
 * Reports the disk that abandoned mezzanines are holding, and clears them when
 * asked. Never on its own, and never the source currently open: rebuilding one
 * means sitting through the encode again.
 */

import { state } from "./state.js";
import { loadEnvironment } from "./environment.js";

/**
 * Reports the disk that abandoned mezzanines are holding, if any.
 *
 * A source that is analysed and not split leaves its mezzanine behind, and on
 * a few-minute source that is about a gigabyte each. The row appears only when
 * there is something to reclaim, so it stays quiet in the normal case.
 *
 * The source currently open is sent along so the server can leave its
 * mezzanine alone — the split still needs it.
 */
async function measureWorkFiles() {
    if (!state.outputDir) return null;

    const query = new URLSearchParams({ output_dir: state.outputDir });
    if (state.sourcePath) query.set("source_path", state.sourcePath);

    try {
        const response = await fetch(`/api/work?${query}`);
        return response.ok ? await response.json() : null;
    } catch {
        // This row is an aside, not the job. Failing to measure disk should
        // never be the thing that interrupts someone mid-split.
        return null;
    }
}

/** Shows what can be reclaimed, or hides the row when there is nothing. */
export async function refreshWorkFiles() {
    const row = document.getElementById("work-row");
    const work = await measureWorkFiles();

    if (!work || work.bytes === 0) {
        row.hidden = true;
        return;
    }

    const sources = work.sources.length;
    document.getElementById("work-detail").textContent =
        `Working files from ${sources} earlier source${sources === 1 ? "" : "s"}` +
        ` — ${work.gb} GB. Clearing means re-analysing to open one again.`;
    document.getElementById("work-clear").hidden = false;
    row.hidden = false;
}

/** Deletes the reclaimable working files, then reports what actually went. */
export async function clearWorkFiles() {
    const button = document.getElementById("work-clear");
    const detail = document.getElementById("work-detail");

    button.disabled = true;
    detail.textContent = "Clearing…";

    try {
        const response = await fetch("/api/work/clear", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                output_dir: state.outputDir,
                source_path: state.sourcePath || null,
            }),
        });

        if (!response.ok) {
            detail.textContent = "Could not clear the working files.";
            return;
        }

        const freed = await response.json();

        // Measure again rather than trusting the total: a file that would not
        // delete is still there, and the row should say so rather than claim
        // everything went
        const remaining = await measureWorkFiles();

        if (remaining && remaining.bytes > 0) {
            await refreshWorkFiles();
            return;
        }

        detail.textContent = `Freed ${freed.gb} GB.`;
        button.hidden = true;

    } finally {
        button.disabled = false;
        // Free space is on the environment panel, and it just changed
        loadEnvironment(true);
    }
}
