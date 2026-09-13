/*
 * Tab Switching.
 *
 * Two features in one page. Switching shows one panel and hides the other, and
 * tells the tab being opened that it is now visible so it can load whatever it
 * needs at that moment rather than on page load.
 *
 * Each tab keeps its own state and its own environment panel. They are
 * separate jobs, often used separately, and one being idle should cost the
 * other nothing.
 */

// Called when a tab becomes visible. Registered rather than imported here, so
// this module stays about switching and knows nothing about what a tab does.
const onShow = {};

/** Runs `handler` the first time a tab is opened, and on every open after. */
export function whenShown(name, handler) {
    onShow[name] = handler;
}

/** Shows one tab and hides the rest. */
export function showTab(name) {
    for (const panel of document.querySelectorAll(".tab-panel")) {
        panel.classList.toggle("active", panel.id === name);
    }

    for (const button of document.querySelectorAll(".tab")) {
        button.classList.toggle("active", button.dataset.tab === name);
    }

    onShow[name]?.();
}

/** Wires every tab button. Called once, from main.js. */
export function wireTabs() {
    for (const button of document.querySelectorAll(".tab")) {
        button.addEventListener("click", () => showTab(button.dataset.tab));
    }
}
