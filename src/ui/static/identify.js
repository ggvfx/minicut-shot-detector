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

import { wireColumns } from "./columns.js";
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
    // The dependency panel and the model picker both live in Setup — set once
    // per machine. This tab gets the one-line health strip and the work.
    loadEnvironment("identifier");
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

    wireNaming();

    document.getElementById("shots-describe")
        .addEventListener("click", () => describeShots(false));
    document.getElementById("shots-redescribe")
        .addEventListener("click", () => describeShots(true));
}

// --- MODEL BACKENDS ---

// The two passes, which are configured identically and independently
/** Wires the naming panel and the table. Called once, from wireIdentifier. */
function wireNaming() {
    wireColumns("identify-table");

    for (const part of ["prefix", "start", "increment", "suffix"]) {
        document.getElementById(`naming-${part}`)
            .addEventListener("input", previewNaming);
    }

    document.getElementById("naming-apply").addEventListener("click", numberShots);
    document.getElementById("identify-rename").addEventListener("click", renameVideos);
    document.getElementById("identify-undo").addEventListener("click", undoRename);
    document.getElementById("identify-export").addEventListener("click", () => exportBreakdown(false));
    document.getElementById("identify-thumbs").addEventListener("click", () => exportBreakdown(true));
}

// --- DESCRIBING A FOLDER ---

/**
 * Describes every shot in the chosen folder, filling the table as they land.
 *
 * The slow call: one vision pass per shot, minutes on a full folder. The
 * server sends each shot back the moment it is readable rather than holding
 * the batch, because a table that stays empty until the end cannot be told
 * from one that has hung — and a run that looks hung gets killed.
 *
 * Each observation is cached server side as it lands, so pressing this again
 * costs nothing for the shots already done.
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
        const response = await fetch("/api/identify/describe/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shots_dir: state.shotsDir, force }),
        });

        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            status.textContent = body.detail || "The shots could not be described.";
            return;
        }

        state.records = [];
        let total = 0;

        for await (const message of ndjson(response)) {
            if (message.error) {
                status.textContent = message.error;
                return;
            }

            if (message.total !== undefined) {
                total = message.total;
                startTable(total);
                continue;
            }

            state.records.push(message);
            appendRecord(message, total);
        }

        status.textContent = "";

    } catch {
        status.textContent = "Could not reach the app.";
    } finally {
        for (const button of buttons) button.disabled = false;
        document.getElementById("identify-progress").hidden = true;
    }
}

/**
 * Reads a newline delimited JSON response, one object at a time.
 *
 * A chunk off the network is not a line: it can hold several, or stop halfway
 * through one. So the tail is kept until the newline that completes it
 * arrives, rather than parsed and dropped.
 */
async function* ndjson(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";

    for (;;) {
        const { value, done } = await reader.read();
        if (done) break;

        pending += decoder.decode(value, { stream: true });
        const lines = pending.split("\n");
        pending = lines.pop();

        for (const line of lines) {
            if (line.trim()) yield JSON.parse(line);
        }
    }

    if (pending.trim()) yield JSON.parse(pending);
}

/** Empties the table and sizes the progress bar for a run of `total` shots. */
function startTable(total) {
    document.getElementById("identify-results-card").hidden = false;
    document.getElementById("identify-actions").hidden = false;
    document.querySelector("#identify-table tbody").innerHTML = "";

    document.getElementById("shots-count").textContent =
        `${total} shot${total === 1 ? "" : "s"}`;

    setProgress(0, total);
    updateVerdict(0, total);
}

/** Adds one finished shot to the table and moves the run along. */
function appendRecord(record, total) {
    document.querySelector("#identify-table tbody").append(recordRow(record));

    const done = state.records.length;
    setProgress(done, total);
    updateVerdict(state.records.filter((one) => one.interpretation).length, total);
}

/**
 * How far along the run is.
 *
 * Determinate now that the total is known up front: "nine of thirty seven"
 * is the difference between waiting and wondering, which an indeterminate
 * sweep could never say.
 */
function setProgress(done, total) {
    const bar = document.querySelector("#identify-progress .progress-bar");
    if (!bar || !total) return;

    bar.style.animation = "none";
    bar.style.width = `${Math.round((done / total) * 100)}%`;
}

function updateVerdict(described, total) {
    const verdict = document.getElementById("identify-verdict");

    verdict.textContent = `${described} of ${total} described`;
    verdict.className = `summary ${described === total ? "ok" : "degraded"}`;
}

/**
 * One row. The shot number is the only editable cell — the rest is evidence.
 *
 * Notes carry failures only — something the person has to act on. The model's
 * own hedging about what it could not tell is kept on the record but stays off
 * the table: a reviewer reads these rows against each other, and a paragraph
 * of reasoning in one of them is noise in every other.
 */
function recordRow(record) {
    const row = document.createElement("tr");
    const reading = record.interpretation ?? {};

    row.append(
        videoCell(record),
        textCell(fileNameOf(record.file), "shot-name"),
        summaryCell(record),
        textCell((reading.characters || []).join(", ") || "—"),
        numberCell(record),
        noteCell(record),
    );

    return row;
}

/**
 * One read-only cell — the filename and the characters.
 *
 * Carries the full text as a tooltip too: a long filename is the one thing
 * here that can still be cut off by its column, and the description and notes
 * beside it are fields that scroll rather than text that clips.
 */
function textCell(value, className = "") {
    const cell = document.createElement("td");
    cell.textContent = value;
    if (value) cell.title = value;
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
/**
 * The shot itself, playable in the row.
 *
 * A description cannot be reviewed without the picture beside it. The poster
 * is the frame the vision pass already sampled, and `preload="none"` means the
 * clip itself is not fetched until someone presses play — so a table of forty
 * rows costs forty small JPEGs, not forty videos.
 */
function videoCell(record) {
    const cell = document.createElement("td");
    const video = document.createElement("video");

    video.className = "shot-video";
    video.controls = true;
    video.preload = "none";
    video.poster = `/api/identify/poster?path=${encodeURIComponent(record.file)}`;
    video.src = `/api/identify/clip?path=${encodeURIComponent(record.file)}`;

    cell.append(video);
    return cell;
}

/**
 * The description, editable.
 *
 * A reviewer corrects a reading as often as they accept it, and the correction
 * is what the export should carry — so this is the field, not a copy of it.
 * It scrolls rather than clamping: a long description has to be readable in
 * the row it belongs to, not only in a tooltip.
 */
function summaryCell(record) {
    const cell = document.createElement("td");
    const input = document.createElement("textarea");

    input.className = "shot-summary-input";
    input.rows = 3;
    input.value = record.interpretation?.summary || "";
    input.placeholder = "—";

    input.addEventListener("change", () => {
        if (!record.interpretation) record.interpretation = {};
        record.interpretation.summary = input.value.trim();
    });

    cell.append(input);
    return cell;
}

/**
 * The notes, editable.
 *
 * Written by both sides: the app puts the reason a shot could not be described
 * here, and the reviewer types over it or adds to it. Whatever the cell holds
 * at the end is what the export writes.
 */
function noteCell(record) {
    const cell = document.createElement("td");
    const input = document.createElement("textarea");

    input.className = "shot-note-input";
    input.rows = 2;
    input.value = record.notes || "";
    input.placeholder = "—";

    input.addEventListener("change", () => {
        record.notes = input.value.trim();
    });

    cell.append(input);
    return cell;
}

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

// --- NAMING THE BATCH ---

/**
 * The four parts, exactly as typed.
 *
 * Nothing is filled in on the user's behalf except the increment, where tens
 * is a real convention rather than a guess. A blank start is left blank so
 * numbering can refuse it: silently numbering forty shots 0010, 0020 under a
 * scheme nobody typed is worse than not numbering them.
 */
function namingScheme() {
    const value = (id) => document.getElementById(id).value.trim();

    return {
        prefix: value("naming-prefix"),
        start: value("naming-start"),
        increment: Number(value("naming-increment")) || 10,
        suffix: value("naming-suffix"),
    };
}

/**
 * Shows what the first two shots would be called, before anything is applied.
 *
 * A naming convention is the kind of thing that looks right until you see it
 * twice: the second name is where a wrong increment becomes obvious.
 */
function previewNaming() {
    const scheme = namingScheme();
    const preview = document.getElementById("naming-preview");

    if (!scheme.start) {
        preview.textContent = "";
        preview.className = "summary";
        return;
    }

    if (!scheme.start.match(/^\d+$/)) {
        preview.textContent = "Start has to be a number";
        preview.className = "summary degraded";
        return;
    }

    const width = scheme.start.length;
    const nameAt = (index) => {
        const number = Number(scheme.start) + (index * scheme.increment);
        return `${scheme.prefix}${String(number).padStart(width, "0")}${scheme.suffix}`;
    };

    preview.textContent = `${nameAt(0)}, then ${nameAt(1)}`;
    preview.className = "summary ok";
}

/** Numbers every row from the scheme. Proposal only — nothing is renamed. */
async function numberShots() {
    const status = document.getElementById("identify-action-status");

    if (!state.records.length) {
        status.textContent = "Describe some shots first.";
        return;
    }

    const scheme = namingScheme();

    if (!scheme.start.match(/^\d+$/)) {
        status.textContent =
            "Fill in Shot naming first — Start has to be the first shot number, "
            + "like 4560.";
        document.querySelector("details.naming").open = true;
        document.getElementById("naming-start").focus();
        return;
    }

    const response = await fetch("/api/identify/number", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ records: state.records, scheme }),
    });

    if (!response.ok) {
        status.textContent = "Those numbers could not be applied.";
        return;
    }

    state.records = await response.json();
    redrawRows();
    status.textContent = `Numbered ${state.records.length} shots. Nothing renamed yet.`;
}

/** Redraws every row from the records, after something changed all of them. */
function redrawRows() {
    const body = document.querySelector("#identify-table tbody");
    body.innerHTML = "";

    for (const record of state.records) {
        body.append(recordRow(record));
    }
}

// --- RENAMING, AND PUTTING IT BACK ---

/**
 * Renames the files on disk.
 *
 * The only destructive button in the app, so it checks first and says exactly
 * what it is about to do. The check is advisory — the server re-runs it before
 * touching anything, because a folder can change while a tab sits open.
 */
async function renameVideos() {
    const status = document.getElementById("identify-action-status");
    const planned = state.records.filter((record) => record.shot_number);

    if (!planned.length) {
        status.textContent = "Number the shots first.";
        return;
    }

    // Pressing this button is the approval. Numbering a batch proposes names
    // and nothing more, and there is no per-row tick in the table — so the
    // approval has to be attached here, at the only moment a person asks for
    // files to be moved. Without it the server finds nothing approved and
    // renames nothing, which is what this did while reporting success.
    for (const record of planned) record.approved = true;

    const body = JSON.stringify({ records: state.records, shots_dir: state.shotsDir });
    const headers = { "Content-Type": "application/json" };

    const check = await fetch("/api/identify/rename/check", { method: "POST", headers, body });
    const problems = (await check.json()).problems || [];

    if (problems.length) {
        status.textContent = problems.join(" · ");
        return;
    }

    status.textContent = `Renaming ${planned.length} files…`;

    const response = await fetch("/api/identify/rename", { method: "POST", headers, body });

    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        status.textContent = detail.detail || "Nothing was renamed.";
        return;
    }

    state.records = await response.json();
    redrawRows();

    // Counted from what came back, not from what was asked for: a status line
    // that reports the plan rather than the result is how a rename that moved
    // nothing announced that it had moved three files.
    const moved = state.records.filter((record) => record.renamed_to).length;

    status.textContent = moved
        ? `Renamed ${moved} files. Undo rename puts them back.`
        : "Nothing was renamed.";
}

/** Puts a renamed batch back to the names it had. */
async function undoRename() {
    const status = document.getElementById("identify-action-status");

    const response = await fetch("/api/identify/rename/undo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ records: state.records, shots_dir: state.shotsDir }),
    });

    if (!response.ok) {
        status.textContent = "Nothing could be put back.";
        return;
    }

    const { restored, records } = await response.json();

    // The table has to follow the folder. Left holding the renamed paths it
    // points at files that are no longer there, so nothing plays and every
    // name reads wrong — worse than the state the undo was recovering from.
    state.records = records;
    redrawRows();

    status.textContent = restored
        ? `Put ${restored} files back.`
        : "There was no rename to undo.";
}

// --- EXPORTING ---

/**
 * Writes the breakdown beside the shots.
 *
 * @param {boolean} thumbnails Whether to bring the stills. Both buttons run
 *   the same route: the spreadsheet's thumbnail column points at these files,
 *   so exporting them separately still has to write the rows they belong to.
 */
async function exportBreakdown(thumbnails) {
    const status = document.getElementById("identify-action-status");

    if (!state.records.length) {
        status.textContent = "There is nothing to export yet.";
        return;
    }

    status.textContent = thumbnails ? "Writing thumbnails…" : "Writing the breakdown…";

    const response = await fetch("/api/identify/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            records: state.records,
            shots_dir: state.shotsDir,
            thumbnails,
        }),
    });

    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        status.textContent = detail.detail || "The export could not be written.";
        return;
    }

    const written = await response.json();
    const stills = thumbnails ? `, and ${written.thumbnails} thumbnails` : "";

    status.textContent = `Wrote ${written.csv} and ${written.xlsx}${stills} to ${written.folder}`;
}
