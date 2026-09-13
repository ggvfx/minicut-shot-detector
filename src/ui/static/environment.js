/*
 * Dependency Panels.
 *
 * Renders what the server says each tab needs. Read only: the panel reports,
 * and every row is something the user can act on.
 *
 * Both panels live in the Setup tab, because setting the app up is a
 * once-per-install job and it was previously split across the two tabs people
 * use daily — which meant a panel nobody reads sitting above the work.
 *
 * The workflow tabs keep a one-line health strip instead: silent when
 * everything is fine, and a link to Setup when it is not.
 *
 * Still two separate panels, because the tabs need genuinely different things —
 * the splitter needs encoders and PySceneDetect, the identifier needs a model
 * and neither of those.
 */

import { state } from "./state.js";
import { showTab } from "./tabs.js";

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
        const report = await response.json();

        renderEnvironment(panel, report);
        renderHealth(tab, report);
    } catch {
        summary.textContent = "Could not reach the app";
        summary.className = "summary blocked";
    }
}

/**
 * The one-line strip on a workflow tab.
 *
 * Hidden entirely when nothing is wrong. A permanent "everything is fine"
 * banner is something people stop reading, and then stop noticing when it
 * changes — the panel has to earn its place on screen each time.
 */
function renderHealth(tab, report) {
    const strip = document.getElementById(`${tab}-health`);
    if (!strip) return;

    if (report.overall === "ok") {
        strip.hidden = true;
        return;
    }

    const problems = report.checks.filter((check) => check.status !== "ok");
    const one = problems.length === 1;

    // The verb has to agree with the count, or the one place the app speaks up
    // about a problem is also the place it looks unfinished
    const subject = one ? "1 thing" : `${problems.length} things`;
    const verb = report.overall === "blocked"
        ? (one ? "needs attention" : "need attention")
        : (one ? "is not set up" : "are not set up");

    strip.textContent = `${subject} ${verb}: `;
    strip.className = `health ${report.overall}`;

    const link = document.createElement("button");
    link.className = "inline-button";
    link.textContent = "Open Setup";
    link.addEventListener("click", () => showTab("setup"));

    strip.append(link);
    strip.hidden = false;
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
