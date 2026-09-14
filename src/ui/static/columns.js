/*
 * Resizable Table Columns.
 *
 * A review table is read across, and how much room each column deserves is the
 * reviewer's call, not ours: one person is checking descriptions against the
 * picture and wants the video wide, the next is scanning shot numbers.
 *
 * Its own module rather than more of identify.js, which is already carrying
 * several jobs. This one knows nothing about shots — give it a table and it
 * makes the columns draggable.
 *
 * Widths are remembered per table for the session, so redrawing rows after a
 * run or a rename does not throw away the layout someone just set up.
 */

// Narrower than this and a column cannot show anything, including its own
// heading — dragging one to nothing looks like the table has lost a column.
const MINIMUM = 60;

const remembered = new Map();

/**
 * Makes every column of a table draggable by its right edge.
 *
 * @param {string} tableId The table's id.
 *
 * Notes:
 *   Fixed layout is what makes this work at all: the browser otherwise sizes
 *   columns from their contents and quietly overrides anything set here.
 */
export function wireColumns(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    // Wiring twice would give every header a second handle stacked on the
    // first, and the one on top would win every drag.
    if (table.dataset.columnsWired) return;
    table.dataset.columnsWired = "yes";

    const headers = [...table.querySelectorAll("thead th")];
    table.style.tableLayout = "fixed";

    // Deliberately not measuring anything here. This runs once, while the tab
    // and the results card are still hidden, where every element measures zero
    // — writing those back as inline widths collapsed all six columns to 0px
    // and left the stylesheet's starting widths with nothing to say. The CSS
    // sizes the table until someone drags it; a drag measures at the moment it
    // happens, when there is something real to measure.
    headers.forEach((header, index) => {
        const handle = document.createElement("span");
        handle.className = "col-resizer";
        handle.title = "Drag to resize";
        header.append(handle);

        handle.addEventListener("pointerdown", (event) => {
            startDrag(event, handle, header, tableId, index);
        });

        // A column dragged to nothing is hard to get back, so the handle
        // offers the way out that costs no dragging at all: drop the inline
        // width and the stylesheet has its column back.
        handle.addEventListener("dblclick", () => {
            header.style.width = "";
            forget(tableId, index);
        });
    });

    restore(tableId, headers);
}

/**
 * Follows the pointer until it is let go, setting the width as it moves.
 *
 * Notes:
 *   The listeners go on the window, not the handle. A drag that ends anywhere
 *   else — off the handle, outside the window, interrupted by the browser —
 *   still has to end: the first version listened on the handle for pointerup,
 *   so a release it never saw left the move listener attached and every later
 *   hover over that edge resized the column with no button held down.
 *
 *   `dragging` is the belt to that braces. Even if a listener outlives its
 *   drag, it does nothing until another pointerdown says a drag has started.
 */
let dragging = null;

function startDrag(event, handle, header, tableId, index) {
    event.preventDefault();

    // Left button only. A right click opening a context menu must not leave a
    // drag running behind it.
    if (event.button !== 0) return;

    dragging = {
        header,
        tableId,
        index,
        startX: event.clientX,

        // Measured now rather than remembered from setup: this is the first
        // moment the column is on screen and has a width worth reading.
        startWidth: header.getBoundingClientRect().width,
    };

    handle.setPointerCapture?.(event.pointerId);
    document.body.classList.add("resizing-column");
}

function onPointerMove(event) {
    if (!dragging) return;

    const width = Math.max(MINIMUM, dragging.startWidth + (event.clientX - dragging.startX));
    dragging.header.style.width = `${width}px`;
}

function endDrag() {
    if (!dragging) return;

    remember(dragging.tableId, dragging.index, dragging.header.style.width);
    dragging = null;
    document.body.classList.remove("resizing-column");
}

// Bound once for the page rather than per handle, and never removed. There is
// nothing to clean up, and nothing to leak: every one of them is a no-op until
// a pointerdown sets `dragging`.
window.addEventListener("pointermove", onPointerMove);
window.addEventListener("pointerup", endDrag);
window.addEventListener("pointercancel", endDrag);
window.addEventListener("blur", endDrag);

function forget(tableId, index) {
    delete remembered.get(tableId)?.[index];
}

function remember(tableId, index, width) {
    if (!remembered.has(tableId)) remembered.set(tableId, {});
    remembered.get(tableId)[index] = width;
}

/** Puts back the widths this table was last dragged to. */
function restore(tableId, headers) {
    const widths = remembered.get(tableId);
    if (!widths) return;

    for (const [index, width] of Object.entries(widths)) {
        if (headers[index]) headers[index].style.width = width;
    }
}
