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
    loadModels();
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

    wireModels();
}

// --- MODEL BACKENDS ---

// The two passes, which are configured identically and independently
const PASSES = ["vision", "text"];

/**
 * Fills both dropdowns from the server's preset list.
 *
 * Built from what the server offers rather than from a list here, so adding a
 * preset is one line in config.py and nothing in the front end.
 */
export async function loadModels() {
    const summary = document.getElementById("models-summary");

    try {
        const response = await fetch("/api/settings");
        if (!response.ok) throw new Error("unreachable");

        const settings = await response.json();
        state.presets = settings.presets;

        for (const pass of PASSES) {
            const select = document.getElementById(`${pass}-preset`);
            select.innerHTML = "";

            for (const preset of settings.presets) {
                const option = document.createElement("option");
                option.value = preset.key;
                option.textContent = preset.label;
                select.append(option);
            }

            select.value = settings[pass].preset;
            document.getElementById(`${pass}-command`).value = (settings[pass].command || []).join(" ");
            showCustomFor(pass);
        }

        summary.textContent = "";
    } catch {
        summary.textContent = "Could not read";
        summary.className = "summary blocked";
    }
}

/** Shows the command box only for "Custom", and the chosen preset's note. */
function showCustomFor(pass) {
    const preset = document.getElementById(`${pass}-preset`).value;
    document.getElementById(`${pass}-command`).hidden = preset !== "custom";

    const note = state.presets?.find((entry) => entry.key === preset)?.note ?? "";
    document.getElementById(`${pass}-note`).textContent = note;
}

/** What one dropdown currently describes, in the shape the API takes. */
function choiceFor(pass) {
    const preset = document.getElementById(`${pass}-preset`).value;
    const typed = document.getElementById(`${pass}-command`).value.trim();

    return { preset, command: preset === "custom" ? typed.split(/\s+/).filter(Boolean) : null };
}

/**
 * Runs one backend and reports what came back.
 *
 * The control that makes this usable by someone who does not work in a
 * terminal: a dropdown can only promise, where this either shows the model's
 * own words or says exactly what went wrong.
 */
async function testModel(pass) {
    const button = document.getElementById(`${pass}-test`);
    const result = document.getElementById(`${pass}-test-result`);

    button.disabled = true;
    result.textContent = "Testing…";
    result.className = "status";

    try {
        const response = await fetch("/api/backends/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(choiceFor(pass)),
        });

        const outcome = await response.json();

        if (outcome.ok) {
            result.textContent = `Answered in ${outcome.seconds}s — "${outcome.detail}"`;
            result.className = "status ok";
        } else {
            result.textContent = outcome.detail;
            result.className = "status blocked";
        }
    } catch {
        result.textContent = "Could not reach the app";
        result.className = "status blocked";
    } finally {
        button.disabled = false;
    }
}

/** Saves both passes, then re-reads the panel that reports on them. */
async function saveModels() {
    const status = document.getElementById("models-save-status");
    status.textContent = "Saving…";

    try {
        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vision: choiceFor("vision"), text: choiceFor("text") }),
        });

        if (!response.ok) throw new Error("refused");

        status.textContent = "Saved";
        // The environment panel reports these, so it is now out of date
        loadEnvironment("identifier", true);
    } catch {
        status.textContent = "Could not save";
    }

    setTimeout(() => { status.textContent = ""; }, 2500);
}

/** Wires the model panel. Called once, from wireIdentifier. */
function wireModels() {
    for (const pass of PASSES) {
        document.getElementById(`${pass}-preset`)
            .addEventListener("change", () => showCustomFor(pass));
        document.getElementById(`${pass}-test`)
            .addEventListener("click", () => testModel(pass));
    }

    document.getElementById("models-save").addEventListener("click", saveModels);
}
