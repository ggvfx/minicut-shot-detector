/*
 * Shared UI State.
 *
 * Everything the front end knows about the job in hand, in one object so it is
 * obvious what exists. Modules import it and read it directly rather than
 * passing it down: there is one page, showing one job, at a time.
 *
 * Grouped by tab. They are separate jobs and one is usually idle, so a field
 * belongs to whichever tab uses it and the shared section stays small.
 */

export const state = {
    // --- SHARED ---
    pickerMode: null,      // "source" | "output" | "shots" | "shotlist" while the dialog is open
    pickerPath: "",        // Directory currently shown in the dialog

    // --- SPLITTER ---
    sourcePath: "",
    outputDir: "",
    probe: null,           // Last ProbeReport from the server
    // The source an output directory was deliberately chosen for. A choice
    // belongs to the job it was made for: the next source suggests its own
    // folder rather than inheriting the last one.
    outputChosenFor: null,
    prepared: null,        // Last PreparedJob: source, mezzanine and proxy
    boundaries: [],        // Frames on which shots start, frame 0 implied
    // Frames only one detector found. Kept separate from the boundaries
    // themselves so a mark placed by hand is never flagged as uncertain.
    uncertain: new Set(),

    // --- IDENTIFIER ---
    shotsDir: "",          // Folder of single-shot files being identified
    shotListPath: "",      // CSV, text document, or folder of named thumbnails
    knowledge: null,       // What the production folder was last found to hold
    records: [],           // One per shot: what was seen, read, and named
    presets: null,         // Backend presets the server offers, for the model dropdowns
};
