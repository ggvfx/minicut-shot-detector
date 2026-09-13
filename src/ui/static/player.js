/*
 * Review Player.
 *
 * The proxy, the transport, the timeline and the marks placed on it, plus the
 * keyboard shortcuts that drive all three.
 *
 * Everything here counts in frames. The proxy carries its frame number burned
 * into the picture so the readout can be checked against it by eye, which is
 * the one thing a frame-accurate player has to get right.
 */

import { state } from "./state.js";

/*
 * Frames, not seconds.
 *
 * The proxy is all-intra, so the browser can seek to any frame exactly. The
 * awkward direction is reading back: currentTime after a seek is a float that
 * does not land cleanly on a frame boundary, and at 23.976 rounding it the
 * obvious way drifts.
 *
 * So we seek to the MIDDLE of a frame's duration, where there is most room
 * either side, and read it back the same way. The frame number burned into the
 * proxy is the check: if the readout and the picture disagree, this is wrong.
 */

/** The source's exact rate as a number — the rational itself lives on the server. */
function frameRate() {
    const source = state.prepared.source;
    return source.fps_numerator / source.fps_denominator;
}

/** The moment at which a frame is unambiguously on screen. */
function secondsForFrame(frame) {
    return (frame + 0.5) / frameRate();
}

/** The frame currently on screen. */
export function currentFrame() {
    const player = document.getElementById("proxy-player");
    return Math.floor(player.currentTime * frameRate());
}

/** Moves to a frame, clamped to the source. */
function goToFrame(frame) {
    const player = document.getElementById("proxy-player");
    const last = state.prepared.source.frame_count - 1;
    const target = Math.max(0, Math.min(frame, last));

    player.currentTime = secondsForFrame(target);
    renderReadout(target);
}

/** Steps forward or back, pausing first — stepping while playing is meaningless. */
export function stepFrames(count) {
    document.getElementById("proxy-player").pause();
    goToFrame(currentFrame() + count);
}

/** Jumps to the nearest marker in a direction, for working cut to cut. */
export function goToCut(direction) {
    const frame = currentFrame();
    const markers = [0, ...state.boundaries];
    const candidates = direction > 0
        ? markers.filter((value) => value > frame)
        : markers.filter((value) => value < frame);

    if (candidates.length === 0) return;

    document.getElementById("proxy-player").pause();
    goToFrame(direction > 0 ? Math.min(...candidates) : Math.max(...candidates));
}

/** Opens the review panel on a freshly prepared job. */
export function openReview() {
    const player = document.getElementById("proxy-player");
    const source = state.prepared.source;

    // Sized by the video's own shape, so it does not sit in a wide box with
    // black either side of it
    player.style.aspectRatio = `${source.width} / ${source.height}`;
    player.src = `/api/proxy?path=${encodeURIComponent(state.prepared.proxy_path)}`;

    document.getElementById("review").hidden = false;
    document.getElementById("output-card").hidden = false;
    document.getElementById("result-card").hidden = true;

    player.addEventListener("loadeddata", () => goToFrame(0), { once: true });

    renderTimeline();
}

/** Hides the review panel — a different source needs a different proxy. */
export function closeReview() {
    document.getElementById("review").hidden = true;
    document.getElementById("output-card").hidden = true;
    document.getElementById("result-card").hidden = true;
    document.getElementById("proxy-player").removeAttribute("src");
    document.getElementById("cut-count").textContent = "";

    state.prepared = null;
    state.boundaries = [];
    state.uncertain = new Set();
}

// ===== MARKERS =====

/**
 * Adds a first frame here, or removes the one already here.
 *
 * Frame 0 always starts the first shot, so it is shown but cannot be removed:
 * there is no shot before it for its frames to join.
 */
export function toggleMarker() {
    if (!state.prepared) return;

    const frame = currentFrame();

    // Frame 0 cannot be unmarked, and its button is disabled to say so
    if (frame === 0) return;

    if (state.boundaries.includes(frame)) {
        state.boundaries = state.boundaries.filter((value) => value !== frame);
    } else {
        state.boundaries = [...state.boundaries, frame].sort((a, b) => a - b);
    }

    // Looked at by a person, so no longer something to look at
    state.uncertain.delete(frame);

    renderTimeline();
    renderReadout(frame);
}

/**
 * Seeks to wherever the strip was pressed, and follows the pointer if it moves.
 *
 * Stepping frame by frame is precise and useless for crossing a thousand
 * frames, so the strip is also the scrubber: drag to somewhere near a cut, then
 * step onto it exactly.
 */
function scrubTo(event) {
    if (!state.prepared) return;

    const timeline = document.getElementById("timeline");
    const bounds = timeline.getBoundingClientRect();
    const fraction = (event.clientX - bounds.left) / bounds.width;
    const clamped = Math.max(0, Math.min(fraction, 1));

    goToFrame(Math.round(clamped * (state.prepared.source.frame_count - 1)));
}

/** Starts a drag, and keeps scrubbing until the pointer is released. */
export function beginScrub(event) {
    if (!state.prepared) return;

    document.getElementById("proxy-player").pause();
    scrubTo(event);
    followPointer();
}

/**
 * Scrubs with the pointer until it is released.
 *
 * Split out because a drag can begin on a tick as well as on bare strip. A
 * tick sits exactly where the playhead does when that frame is the current
 * one, so a press there has to be able to become a drag — otherwise the
 * playhead is unreachable whenever it is parked on a shot start, which is
 * precisely where a review leaves it.
 */
function followPointer() {
    // Listening on the window means the drag survives leaving the strip, which
    // is what anyone dragging quickly will do
    window.addEventListener("pointermove", scrubTo);
    window.addEventListener("pointerup", endScrub, { once: true });
}

function endScrub() {
    window.removeEventListener("pointermove", scrubTo);
}

/** Moves the playhead to where the player actually is. */
function renderPlayhead(frame) {
    const playhead = document.getElementById("playhead");
    const last = state.prepared.source.frame_count - 1;
    playhead.style.left = `${(frame / last) * 100}%`;
}

/** Draws a tick for every first frame, placed where it falls in the source. */
function renderTimeline() {
    const timeline = document.getElementById("timeline");
    const last = state.prepared.source.frame_count - 1;
    timeline.innerHTML = "";

    // The playhead lives on the strip too, so it is redrawn with the ticks
    const playhead = document.createElement("div");
    playhead.id = "playhead";
    playhead.className = "playhead";
    timeline.append(playhead);

    // Frame 0 is a first frame too, drawn differently because it is fixed
    for (const frame of [0, ...state.boundaries]) {
        const tick = document.createElement("button");

        // Three states: the fixed start, an agreed cut, and one only a single
        // detector found — which is where a review should begin
        const uncertain = state.uncertain.has(frame);
        tick.className = frame === 0 ? "tick fixed" : `tick${uncertain ? " uncertain" : ""}`;
        tick.style.left = `${(frame / last) * 100}%`;
        tick.title = uncertain
            ? `Frame ${frame} — found by one detector, worth a look`
            : `Frame ${frame}`;
        // Stops the strip from handling the press as well, so the frame comes
        // from the tick exactly rather than from where the pixel landed — then
        // picks the drag up itself, so a press here is still a grab
        tick.addEventListener("pointerdown", (event) => {
            event.stopPropagation();
            event.preventDefault();
            document.getElementById("proxy-player").pause();
            goToFrame(frame);
            followPointer();
        });
        timeline.append(tick);
    }

    const shots = state.boundaries.length + 1;
    const toCheck = state.boundaries.filter((frame) => state.uncertain.has(frame)).length;

    document.getElementById("cut-count").textContent =
        `${shots} shot${shots === 1 ? "" : "s"}` +
        (toCheck > 0 ? ` · ${toCheck} to check` : "");
}

/** Shows the current frame, and what the mark button would do to it. */
export function renderReadout(frame) {
    const last = state.prepared.source.frame_count - 1;
    document.getElementById("frame-readout").textContent = `Frame ${frame} of ${last}`;
    renderPlayhead(frame);

    const marked = frame === 0 || state.boundaries.includes(frame);
    const button = document.getElementById("mark-button");
    button.textContent = marked ? "Remove first frame" : "Mark first frame";
    button.disabled = frame === 0;

    // Same colours as the ticks, so scrubbing through the picture reads the
    // same way as scanning the strip: green for a shot start, amber for one
    // only a single detector found
    const marker = document.getElementById("frame-marker");
    marker.hidden = !marked;
    marker.className = state.uncertain.has(frame) ? "frame-marker uncertain" : "frame-marker";
    marker.title = marked ? `Frame ${frame} starts a shot` : "";

    // The number is burned into the picture, so the dot has to be placed
    // around it. Its width is set by the LONGEST frame number in the source,
    // not the current one, so the dot holds still while scrubbing — a marker
    // that shifts as the counter gains a digit is harder to scan than one that
    // sits in the same place all the way through. Percentages of the player's
    // width, matching the CSS: the counter starts 8px in and each monospaced
    // digit advances about 12.7px, in a frame that is always 640 wide.
    const digits = String(last).length;
    marker.style.left = `${1.25 + digits * 1.98 + 0.6}%`;
}

// ===== KEYBOARD =====

/**
 * Transport shortcuts, so review can be done without leaving the keyboard.
 *
 * Ignored while typing in a field, or the path box could not contain an "f".
 */
export function handleKey(event) {
    if (!state.prepared || document.getElementById("review").hidden) return;

    const typing = ["INPUT", "TEXTAREA"].includes(event.target.tagName);
    if (typing) return;

    const step = event.shiftKey ? 10 : 1;
    const actions = {
        ArrowLeft: () => stepFrames(-step),
        ArrowRight: () => stepFrames(step),
        "[": () => goToCut(-1),
        "]": () => goToCut(1),
        f: toggleMarker,
        F: toggleMarker,
        " ": togglePlay,
    };

    const action = actions[event.key];
    if (action) {
        event.preventDefault();
        action();
    }
}

/** Play or pause, and keep the button's label honest. */
export function togglePlay() {
    const player = document.getElementById("proxy-player");
    const button = document.getElementById("play-button");

    if (player.paused) {
        player.play();
        button.textContent = "Pause";
    } else {
        player.pause();
        button.textContent = "Play";
    }
}
