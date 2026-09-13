/*
 * The Identifier Tab.
 *
 * Describes a folder of single-shot files, matches each to a shot number, and
 * hands the result to a person to correct before anything is renamed.
 *
 * **First pass.** The environment panel, the production knowledge section and
 * the path pickers are live. Describing, matching, renaming and exporting are
 * laid out with their controls disabled — the pipeline behind them is written
 * as a skeleton and not yet implemented, and a button that looks ready and
 * does nothing is worse than one that says it is not.
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

// --- OPENING THE TAB ---

/**
 * Loads everything the tab shows, each time it becomes visible.
 *
 * On open rather than on page load: someone who only uses the Splitter should
 * never pay for a model availability check they will not read.
 */
export function openIdentifier() {
    loadEnvironment("identifier");
    loadKnowledge();
}

/** Wires the tab's controls. Called once, from main.js. */
export function wireIdentifier() {
    const recheck = document.getElementById("identifier-recheck-button");

    // Inside the <summary>, so its click must not also open or close the panel
    recheck.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        loadEnvironment("identifier", true);
        loadKnowledge();
    });
    recheck.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            loadEnvironment("identifier", true);
            loadKnowledge();
        }
    });

    // Typed paths are as valid as picked ones, the same as on the Splitter
    document.getElementById("shots-dir")
        .addEventListener("change", (event) => { state.shotsDir = event.target.value; });

    document.getElementById("shotlist-path")
        .addEventListener("change", (event) => { state.shotListPath = event.target.value; });
}
