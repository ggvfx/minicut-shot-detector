/*
 * Dependency Panel.
 *
 * Renders what the server says about ffmpeg, the encoders and free space. Read
 * only: the panel reports, and every row is something the user can act on.
 */

import { state } from "./state.js";

/**
 * Fetches the dependency report and renders it.
 * @param {boolean} refresh - True re-runs the checks instead of using the cache.
 */
export async function loadEnvironment(refresh = false) {
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
