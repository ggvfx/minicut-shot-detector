/*
 * The Setup Tab.
 *
 * Everything you do once: what is installed, and how to install it.
 *
 * The model picker lives here. It started on the Identifier tab on the
 * grounds that which model runs a batch is a per-job decision — but in use it
 * is set once per machine, like ffmpeg, and the panels above already report
 * which CLI is configured. Picker in one tab and report in another was the
 * confusing part.
 *
 * Loading the production's own knowledge is still NOT here: that genuinely
 * does change per job, and it belongs beside the work.
 *
 * Its own tab because setting the app up is not a workflow. It used to be
 * split across the two tabs people use daily, which meant setting up meant
 * visiting both, and left a panel nobody reads sitting above the work. Those
 * tabs now carry a one-line health strip that is silent unless something is
 * wrong, and links here when it is.
 */

import { loadEnvironment } from "./environment.js";
import { state } from "./state.js";

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

// --- MODEL BACKENDS ---

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


// --- OPENING THE TAB ---

/** Loads everything this tab shows, each time it becomes visible. */
export function openSetup() {
    loadEnvironment("splitter");
    loadEnvironment("identifier");
    loadModels();
    loadGuide();
}

/** Wires the tab's controls. Called once, from main.js. */
export function wireSetup() {
    for (const pass of PASSES) {
        document.getElementById(`${pass}-preset`)
            .addEventListener("change", () => showCustomFor(pass));
        document.getElementById(`${pass}-test`)
            .addEventListener("click", () => testModel(pass));
    }

    document.getElementById("models-save").addEventListener("click", saveModels);

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
