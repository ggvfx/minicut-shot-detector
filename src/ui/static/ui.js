/*
 * Shared Display Helpers.
 *
 * Anything used by more than one module and owning no state of its own. A
 * helper used by a single module belongs in that module instead — the same
 * rule the Python side applies to core/utils.py.
 */

/**
 * Shows or hides the working indicator.
 *
 * It reports that work is happening, not how far along it is. Per-stage
 * progress needs streaming, which is its own task, and a percentage invented
 * here would be a lie told confidently.
 */
export function showProgress(running) {
    document.getElementById("progress").hidden = !running;
}
