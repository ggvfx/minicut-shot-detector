/*
 * The Setup Tab.
 *
 * Everything you do once: what is installed, and where the production's
 * character sheet lives.
 *
 * Choosing a model is deliberately NOT here. Which tool runs a batch is a
 * per-job decision in a way that installing ffmpeg is not, so it sits on the
 * Identifier tab with the work it affects.
 *
 * Its own tab because setting the app up is not a workflow. It used to be
 * split across the two tabs people use daily, which meant setting up meant
 * visiting both, and left a panel nobody reads sitting above the work. Those
 * tabs now carry a one-line health strip that is silent unless something is
 * wrong, and links here when it is.
 */

import { loadEnvironment } from "./environment.js";
import { state } from "./state.js";

// --- PRODUCTION KNOWLEDGE ---

/**
 * Reports what the production folder holds.
 *
 * Read on every open rather than once, because the whole point of a folder
 * over an upload is that someone edits a character sheet in another window and
 * expects it picked up.
 */
export async function loadKnowledge() {
    const summary = document.getElementById("knowledge-summary");
    const facts = document.getElementById("knowledge-facts");
    const status = document.getElementById("knowledge-status");

    try {
        const response = await fetch("/api/knowledge");
        if (!response.ok) throw new Error("unreachable");

        const knowledge = await response.json();
        state.knowledge = knowledge;

        renderFactsInto(facts, {
            Folder: knowledge.directory,
            Characters: describeFile(knowledge.characters),
            Terminology: describeFile(knowledge.terminology),
        });

        const found = [knowledge.characters.found, knowledge.terminology.found].filter(Boolean);
        summary.textContent = found.length === 2 ? "Loaded" : `${found.length} of 2 files`;
        summary.className = `summary ${found.length === 2 ? "ok" : "degraded"}`;

        // Neither file is required, so say what their absence costs rather
        // than treating it as an error
        status.textContent = found.length === 2
            ? ""
            : "Shots will still be described, in plain words, with nobody named.";

    } catch {
        summary.textContent = "Could not read";
        summary.className = "summary blocked";
        status.textContent = "The production folder could not be read.";
    }
}

/** A file's state in words, since "true" tells a reader nothing. */
function describeFile(file) {
    if (!file.found) return "Not found";
    return `Found — ${file.characters.toLocaleString()} characters`;
}

/** Renders a label/value map into a definition list. */
function renderFactsInto(list, facts) {
    list.innerHTML = "";

    for (const [label, value] of Object.entries(facts)) {
        const term = document.createElement("dt");
        term.textContent = label;

        const definition = document.createElement("dd");
        definition.textContent = value;

        list.append(term, definition);
    }
}

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
    loadKnowledge();
    loadGuide();
}

/** Wires the tab's controls. Called once, from main.js. */
export function wireSetup() {
    for (const [tab, id] of [["splitter", "recheck-button"], ["identifier", "identifier-recheck-button"]]) {
        const recheck = document.getElementById(id);

        const refresh = () => {
            loadEnvironment(tab, true);
            loadKnowledge();
        };

        recheck.addEventListener("click", refresh);
        recheck.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                refresh();
            }
        });
    }
}
