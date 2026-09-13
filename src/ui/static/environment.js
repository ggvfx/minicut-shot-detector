/*
 * Dependency Panel.
 *
 * Renders what the server says a tab needs. Read only: the panel reports, and
 * every row is something the user can act on.
 *
 * One panel per tab, because the two need genuinely different things — the
 * splitter needs encoders and PySceneDetect, the identifier needs a model and
 * neither of those. Showing each the other's requirements would put rows in
 * front of people who cannot act on them.
 */

import { state } from "./state.js";

// Which elements each tab's panel draws into. The splitter's are unprefixed
// because it was here first and renaming its ids would churn the HTML for
// nothing.
const PANELS = {
    splitter: {
        summary: "environment-summary",
        checks: "environment-checks",
    },
    identifier: {
        summary: "identifier-environment-summary",
        checks: "identifier-environment-checks",
    },
};

const WORDING = {
    ok: "Ready",
    degraded: "Ready, with limitations",
    blocked: "Cannot run yet",
};

/**
 * Fetches one tab's dependency report and renders it.
 *
 * @param {string} tab - "splitter" or "identifier".
 * @param {boolean} refresh - True re-runs the checks instead of using the cache.
 */
export async function loadEnvironment(tab = "splitter", refresh = false) {
    const panel = PANELS[tab];
    const summary = document.getElementById(panel.summary);
    summary.textContent = "Checking…";

    const params = new URLSearchParams({ tab });

    // Only the splitter has an output directory to measure against; the
    // identifier writes almost nothing and has not chosen one at this point
    if (tab === "splitter" && state.outputDir) params.set("output_dir", state.outputDir);
    if (refresh) params.set("refresh", "true");

    try {
        const response = await fetch(`/api/environment?${params}`);
        renderEnvironment(panel, await response.json());
    } catch {
        summary.textContent = "Could not reach the app";
        summary.className = "summary blocked";
    }
}

/**
 * Draws one report into one panel.
 *
 * Three states, not two: "degraded" is a warning the user may proceed past.
 */
function renderEnvironment(panel, report) {
    const summary = document.getElementById(panel.summary);
    const list = document.getElementById(panel.checks);

    summary.textContent = `${WORDING[report.overall]} — ${report.platform}`;
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

        // Every failure carries a short guide to resolving it — usually a
        // package-manager line plus a download that needs no package manager,
        // because one command assumes a tool the user may not have.
        for (const fix of check.fixes ?? []) row.append(fixRow(fix));

        list.append(row);
    }
}

/**
 * One line of the guide under a failing check.
 *
 * Three shapes: a command to paste, a page to open, or a plain instruction.
 * A command is presented as a thing to do rather than text to read — someone
 * who does not live in a terminal needs to be shown that they need not retype
 * it — and the copy confirms, because silent copying leaves people clicking
 * repeatedly and unsure whether it worked.
 */
function fixRow(fix) {
    const wrapper = document.createElement("div");
    wrapper.className = "check-fix";

    const hint = document.createElement("span");
    hint.className = "fix-hint";
    hint.textContent = fix.label;
    wrapper.append(hint);

    if (fix.command) {
        const line = document.createElement("code");
        line.className = "fix-command";
        line.textContent = fix.command;

        const copy = document.createElement("button");
        copy.className = "secondary fix-copy";
        copy.textContent = "Copy";

        const doCopy = async () => {
            try {
                await navigator.clipboard.writeText(fix.command);
                copy.textContent = "Copied";
            } catch {
                // Clipboard access can be refused; selecting it by hand still works
                copy.textContent = "Select and press Ctrl+C";
            }
            setTimeout(() => { copy.textContent = "Copy"; }, 2000);
        };

        copy.addEventListener("click", doCopy);
        line.addEventListener("click", doCopy);
        wrapper.append(line, copy);
    }

    if (fix.url) {
        const link = document.createElement("a");
        link.className = "fix-link";
        link.href = fix.url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = fix.url;
        wrapper.append(link);
    }

    return wrapper;
}
