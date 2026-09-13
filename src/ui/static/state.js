/*
 * Shared UI State.
 *
 * Everything the front end knows about the job in hand, in one object so it is
 * obvious what exists. Modules import it and read it directly rather than
 * passing it down: there is one page, showing one job, at a time.
 */

// Everything the UI knows. Kept in one object so it is obvious what exists.
export const state = {
    sourcePath: "",
    outputDir: "",
    pickerMode: null,      // "source" | "output" while the dialog is open
    pickerPath: "",        // Directory currently shown in the dialog
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
};
