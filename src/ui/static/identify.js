/*
 * The Identifier Tab.
 *
 * Describes a folder of single-shot files, matches each to a shot number, and
 * hands the result to a person to correct before anything is renamed.
 *
 * Setting the app up is not here: the dependency panels and the install guides
 * are in the Setup tab, because they are done once and this tab is used daily.
 * Choosing a model and loading the show's own knowledge *are* here, because
 * both are per-job decisions in a way that installing ffmpeg is not.
 *
 * **First pass.** The path pickers and the health strip are live. Describing,
 * matching, renaming and exporting are laid out with their controls disabled —
 * the pipeline behind them is a skeleton, and a button that looks ready and
 * does nothing is worse than one that says it is not.
 */

import { loadEnvironment } from "./environment.js";
import { state } from "./state.js";
import { fileNameOf } from "./ui.js";

// --- PRODUCTION KNOWLEDGE ---

/**
 * Reports what the production file holds, by category.
 *
 * Read on every open rather than once, because the whole point of a folder
 * over an upload is that someone edits the file in another window and expects
 * it picked up.
 *
 * Counts rather than contents: "20 characters, 5 props" is the cheapest way to
 * see the file was read the way it was meant, and a heading typed at the wrong
 * level shows up here as a category with nothing in it.
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
            File: knowledge.file,
            Folder: knowledge.directory,
            Found: describeCounts(knowledge),
        });

        summary.textContent = knowledge.found ? summarise(knowledge) : "No file yet";
        summary.className = `summary ${knowledge.found ? "ok" : "degraded"}`;

        // Not required, so say what its absence costs rather than calling it
        // an error — a show with no list yet is exactly who the breakdown
        // export is for
        status.textContent = knowledge.found
            ? "Edit the file and press Re-read to pick up changes."
            : `Put a ${knowledge.file} in the folder above to have shots named. `
              + "Without it every shot is still described, just with nobody named.";

    } catch {
        summary.textContent = "Could not read";
        summary.className = "summary blocked";
        status.textContent = "The production folder could not be read.";
    }
}

/** "3 characters, 2 props, 3 environments", or what is missing. */
function describeCounts(knowledge) {
    if (!knowledge.found) return "Nothing yet";

    const parts = knowledge.categories
        .filter((name) => name in knowledge.counts)
        .map((name) => `${knowledge.counts[name]} ${trimPlural(name, knowledge.counts[name])}`);

    return parts.length ? parts.join(", ") : "No category headings found";
}

/** The short version for the panel header. */
function summarise(knowledge) {
    const total = Object.values(knowledge.counts).reduce((sum, n) => sum + n, 0);
    return total ? `${total} ${total === 1 ? "entry" : "entries"}` : "Nothing read";
}

/** "1 character" rather than "1 characters". */
function trimPlural(name, count) {
    return count === 1 ? name.replace(/s$/, "") : name;
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
    // The dependency panel itself lives in Setup; this tab gets the one-line
    // health strip, and the model picker that belongs with the work
    loadEnvironment("identifier");
    loadModels();
    loadKnowledge();
}

/** Wires the tab's controls. Called once, from main.js. */
export function wireIdentifier() {
    // Editing the file in another window and pressing this is the whole point
    // of a folder over an upload
    const reread = document.getElementById("knowledge-recheck");
    reread.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        loadKnowledge();
    });
    reread.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            loadKnowledge();
        }
    });

    // Typed paths are as valid as picked ones, the same as on the Splitter
    document.getElementById("shots-dir")
        .addEventListener("change", (event) => { state.shotsDir = event.target.value; });

    document.getElementById("shotlist-path")
        .addEventListener("change", (event) => { state.shotListPath = event.target.value; });

    wireModels();

    document.getElementById("shots-describe")
        .addEventListener("click", () => describeShots(false));
    document.getElementById("shots-redescribe")
        .addEventListener("click", () => describeShots(true));
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

// --- DESCRIBING A FOLDER ---

/**
 * Describes every shot in the chosen folder and fills in the table.
 *
 * The slow call: one vision pass per shot. It says so rather than pretending
 * otherwise, and the server caches each observation as it lands, so pressing
 * this again costs nothing for the shots already done.
 */
async function describeShots(force = false) {
    const status = document.getElementById("identify-status");
    const buttons = [
        document.getElementById("shots-describe"),
        document.getElementById("shots-redescribe"),
    ];

    if (!state.shotsDir) {
        status.textContent = "Choose a folder of shots first.";
        return;
    }

    for (const button of buttons) button.disabled = true;
    document.getElementById("identify-progress").hidden = false;
    status.textContent = force
        ? "Describing every shot again…"
        : "Describing… one model call per shot, so this takes a while.";

    try {
        const response = await fetch("/api/identify/describe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shots_dir: state.shotsDir, force }),
        });

        const body = await response.json();

        if (!response.ok) {
            status.textContent = body.detail || "The shots could not be described.";
            return;
        }

        state.records = body;
        status.textContent = "";
        renderRecords(body);

    } catch {
        status.textContent = "Could not reach the app.";
    } finally {
        for (const button of buttons) button.disabled = false;
        document.getElementById("identify-progress").hidden = true;
    }
}

/** Draws one row per shot, with the shot number editable. */
function renderRecords(records) {
    document.getElementById("identify-results-card").hidden = false;
    document.getElementById("identify-actions").hidden = false;

    const described = records.filter((record) => record.interpretation);
    document.getElementById("shots-count").textContent =
        `${records.length} shot${records.length === 1 ? "" : "s"}`;
    document.getElementById("identify-verdict").textContent =
        `${described.length} of ${records.length} described`;
    document.getElementById("identify-verdict").className =
        `summary ${described.length === records.length ? "ok" : "degraded"}`;

    const body = document.querySelector("#identify-table tbody");
    body.innerHTML = "";

    for (const record of records) {
        body.append(recordRow(record));
    }
}

/** One row. The shot number is the only editable cell — the rest is evidence. */
function recordRow(record) {
    const row = document.createElement("tr");
    const reading = record.interpretation ?? {};

    row.append(
        textCell(fileNameOf(record.file), "shot-name"),
        textCell(reading.summary || "—", "shot-summary"),
        textCell((reading.characters || []).join(", ") || "—"),
        numberCell(record),
        textCell(record.notes || "", "shot-note"),
    );

    return row;
}

function textCell(value, className = "") {
    const cell = document.createElement("td");
    cell.textContent = value;
    if (className) cell.className = className;
    return cell;
}

/**
 * The shot number, editable.
 *
 * Blank is a legitimate answer — a shot nothing could place is left for a
 * person rather than guessed at — so the field starts empty and says what it
 * is for rather than pretending to have an opinion.
 */
function numberCell(record) {
    const cell = document.createElement("td");
    const input = document.createElement("input");

    input.type = "text";
    input.className = "shot-number";
    input.value = record.shot_number || "";
    input.placeholder = "—";

    // Held on the record rather than read back off the table later: the table
    // is a view, and the records are what an export or a rename will use
    input.addEventListener("change", () => {
        record.shot_number = input.value.trim();
        record.approved = Boolean(record.shot_number);
    });

    cell.append(input);
    return cell;
}
