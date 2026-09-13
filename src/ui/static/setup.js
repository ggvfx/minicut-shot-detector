/*
 * The Setup Tab.
 *
 * Everything you do once: what is installed, and how to install it.
 *
 * Choosing a model and loading the production's own knowledge are deliberately
 * NOT here. Both are per-job decisions in a way that installing ffmpeg is not,
 * so they sit on the Identifier tab with the work they affect.
 *
 * Its own tab because setting the app up is not a workflow. It used to be
 * split across the two tabs people use daily, which meant setting up meant
 * visiting both, and left a panel nobody reads sitting above the work. Those
 * tabs now carry a one-line health strip that is silent unless something is
 * wrong, and links here when it is.
 */

import { loadEnvironment } from "./environment.js";

// --- INSTALL GUIDE ---

/**
 * What to install, whatever state the machine is in.
 *
 * The checks above only speak up when something is missing. This is for the
 * person setting up a second machine, or working out what to tell a colleague
 * before sending them the folder.
 */
export async function loadGuide() {
    const list = document.getElementById("guide-list");

    try {
        const response = await fetch("/api/guide");
        if (!response.ok) throw new Error("unreachable");

        const guide = await response.json();
        document.getElementById("guide-platform").textContent = guide.platform;

        list.innerHTML = "";
        for (const item of [guide.python, guide.ffmpeg]) {
            const term = document.createElement("dt");
            term.textContent = item.label;

            const options = document.createElement("dd");
            for (const fix of item.fixes) options.append(guideRow(fix));

            list.append(term, options);
        }
    } catch {
        list.innerHTML = "";
    }
}

/** One install option: a command to copy, or a page to open. */
function guideRow(fix) {
    const row = document.createElement("div");
    row.className = "check-fix";

    const label = document.createElement("span");
    label.className = "fix-hint";
    label.textContent = fix.label;
    row.append(label);

    if (fix.command) {
        const line = document.createElement("code");
        line.className = "fix-command";
        line.textContent = fix.command;
        line.title = "Click to copy";
        line.addEventListener("click", () => navigator.clipboard.writeText(fix.command));
        row.append(line);
    }

    if (fix.url) {
        const link = document.createElement("a");
        link.className = "fix-link";
        link.href = fix.url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = fix.url;
        row.append(link);
    }

    return row;
}

// --- OPENING THE TAB ---

/** Loads everything this tab shows, each time it becomes visible. */
export function openSetup() {
    loadEnvironment("splitter");
    loadEnvironment("identifier");
    loadGuide();
}

/** Wires the tab's controls. Called once, from main.js. */
export function wireSetup() {
    for (const [tab, id] of [["splitter", "recheck-button"], ["identifier", "identifier-recheck-button"]]) {
        const recheck = document.getElementById(id);

        const refresh = () => loadEnvironment(tab, true);

        recheck.addEventListener("click", refresh);
        recheck.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                refresh();
            }
        });
    }
}
