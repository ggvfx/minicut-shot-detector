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

/** Follows the pointer until it is let go, setting the width as it moves. */
function startDrag(event, handle, header, tableId, index) {
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);

    const startX = event.clientX;

    // Measured now rather than remembered from setup: this is the first moment
    // the column is on screen and has a width worth reading.
    const startWidth = header.getBoundingClientRect().width;

    const move = (moved) => {
        const width = Math.max(MINIMUM, startWidth + (moved.clientX - startX));
        header.style.width = `${width}px`;
    };

    const release = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", release);
        remember(tableId, index, header.style.width);
    };

    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", release);
}

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
