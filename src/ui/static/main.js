/*
 * Wiring.
 *
 * The one module the page loads. Everything else is imported from here, and
 * nothing else attaches a listener — so the answer to "what happens when this
 * is clicked" is always in this file.
 */

import { state } from "./state.js";
import { loadEnvironment } from "./environment.js";
import { openIdentifier, wireIdentifier } from "./identify.js";
import { analyseSource, inspectSource } from "./source.js";
import {
    beginScrub,
    currentFrame,
    goToCut,
    handleKey,
    renderReadout,
    stepFrames,
    toggleMarker,
    togglePlay,
} from "./player.js";
import { splitSource } from "./splitting.js";
import { clearWorkFiles, refreshWorkFiles } from "./work.js";
import { choosePath, openPicker } from "./picker.js";
import { whenShown, wireTabs } from "./tabs.js";

document.addEventListener("DOMContentLoaded", () => {
    loadEnvironment("splitter");

    // The Identifier loads what it shows when it is opened, not on page load:
    // someone who only uses the Splitter should never pay for a model
    // availability check they will not read.
    wireTabs();
    wireIdentifier();
    whenShown("identifier", openIdentifier);

    // Inside the <summary>, so its click must not also open or close the panel
    const recheck = document.getElementById("recheck-button");
    recheck.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        loadEnvironment("splitter", true);
    });
    recheck.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            loadEnvironment("splitter", true);
        }
    });

    for (const button of document.querySelectorAll("[data-picker]")) {
        button.addEventListener("click", () => openPicker(button.dataset.picker));
    }

    document.getElementById("picker-close")
        .addEventListener("click", () => document.getElementById("picker").close());

    // "Choose this folder" applies to the directory currently shown
    document.getElementById("picker-choose")
        .addEventListener("click", () => choosePath(state.pickerPath));

    document.getElementById("inspect-button").addEventListener("click", inspectSource);
    document.getElementById("analyse-button").addEventListener("click", analyseSource);
    document.getElementById("split-button").addEventListener("click", splitSource);

    // Transport
    document.getElementById("play-button").addEventListener("click", togglePlay);
    document.getElementById("step-back").addEventListener("click", (e) => stepFrames(e.shiftKey ? -10 : -1));
    document.getElementById("step-forward").addEventListener("click", (e) => stepFrames(e.shiftKey ? 10 : 1));
    document.getElementById("previous-cut").addEventListener("click", () => goToCut(-1));
    document.getElementById("next-cut").addEventListener("click", () => goToCut(1));
    document.getElementById("mark-button").addEventListener("click", toggleMarker);
    document.getElementById("timeline").addEventListener("pointerdown", beginScrub);

    // The readout follows playback as well as stepping
    document.getElementById("proxy-player")
        .addEventListener("timeupdate", () => {
            if (state.prepared) renderReadout(currentFrame());
        });

    document.addEventListener("keydown", handleKey);

    // Typed paths are as valid as picked ones
    document.getElementById("source-path")
        .addEventListener("change", (event) => { state.sourcePath = event.target.value; });

    document.getElementById("output-dir")
        .addEventListener("change", (event) => {
            state.outputDir = event.target.value;
            // Typed by hand, so it is as deliberate as one picked from the
            // dialog, and belongs to the source currently loaded
            state.outputChosenFor = state.sourcePath;
            loadEnvironment("splitter", true);
            refreshWorkFiles();
        });

    document.getElementById("work-clear").addEventListener("click", clearWorkFiles);
});
