/*
 * Administration -> Platform -> Compute / Storage.
 *
 * dash-mantine-components 0.14.1 ships no drag-and-drop component, so the board
 * is plain HTML5 DnD driven from here. Everything is delegated off `document`
 * so the handlers survive Dash re-rendering the board (scope change, save,
 * reset) without any re-attach step.
 *
 * The board publishes `{family: mode}` into the `csc-board-state` dcc.Store via
 * `dash_clientside.set_props`; the Save callback reads that Store.
 */
(function () {
    "use strict";

    var BOARD_ID = "csc-board";
    var STORE_ID = "csc-board-state";
    var CARD_SEL = "[data-coupling-card]";
    var BODY_SEL = "[data-coupling-zone-body]";

    var dragged = null;

    function board() {
        return document.getElementById(BOARD_ID);
    }

    function cardsIn(zoneBody) {
        return zoneBody.querySelectorAll(CARD_SEL);
    }

    /** Read the DOM, refresh the visual state, push `{family: mode}` to Dash. */
    function publish() {
        var root = board();
        if (!root) {
            return;
        }
        var state = {};
        Array.prototype.forEach.call(root.querySelectorAll(CARD_SEL), function (card) {
            var body = card.closest(BODY_SEL);
            if (!body) {
                return;
            }
            var mode = body.getAttribute("data-mode");
            state[card.getAttribute("data-family")] = mode;
            card.classList.toggle("csc-card--dirty", mode !== card.getAttribute("data-initial-mode"));
        });

        Array.prototype.forEach.call(root.querySelectorAll(BODY_SEL), function (body) {
            var count = cardsIn(body).length;
            var counter = root.querySelector('[data-zone-count="' + body.getAttribute("data-mode") + '"]');
            if (counter) {
                counter.textContent = String(count);
            }
            body.classList.toggle("csc-zone-body--empty", count === 0);
        });

        var cs = window.dash_clientside;
        if (cs && typeof cs.set_props === "function") {
            cs.set_props(STORE_ID, { data: state });
        }
    }

    function clearDropHints() {
        var root = board();
        if (!root) {
            return;
        }
        Array.prototype.forEach.call(root.querySelectorAll(BODY_SEL), function (body) {
            body.classList.remove("csc-zone-body--over");
        });
    }

    /** Move a card into a zone body, keeping the cards alphabetical. */
    function place(card, zoneBody) {
        if (!card || !zoneBody || card.closest(BODY_SEL) === zoneBody) {
            return false;
        }
        var family = card.getAttribute("data-family") || "";
        var before = null;
        Array.prototype.forEach.call(cardsIn(zoneBody), function (other) {
            if (before === null && (other.getAttribute("data-family") || "") > family) {
                before = other;
            }
        });
        zoneBody.insertBefore(card, before);
        return true;
    }

    document.addEventListener("dragstart", function (ev) {
        var card = ev.target && ev.target.closest ? ev.target.closest(CARD_SEL) : null;
        if (!card || !board() || !board().contains(card)) {
            return;
        }
        dragged = card;
        card.classList.add("csc-card--dragging");
        if (ev.dataTransfer) {
            ev.dataTransfer.effectAllowed = "move";
            // Firefox refuses to start a drag without payload.
            ev.dataTransfer.setData("text/plain", card.getAttribute("data-family") || "");
        }
    });

    document.addEventListener("dragend", function () {
        if (dragged) {
            dragged.classList.remove("csc-card--dragging");
        }
        dragged = null;
        clearDropHints();
    });

    document.addEventListener("dragover", function (ev) {
        if (!dragged) {
            return;
        }
        var body = ev.target && ev.target.closest ? ev.target.closest(BODY_SEL) : null;
        if (!body) {
            return;
        }
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = "move";
        }
        clearDropHints();
        body.classList.add("csc-zone-body--over");
    });

    document.addEventListener("dragleave", function (ev) {
        var body = ev.target && ev.target.closest ? ev.target.closest(BODY_SEL) : null;
        if (body) {
            body.classList.remove("csc-zone-body--over");
        }
    });

    document.addEventListener("drop", function (ev) {
        if (!dragged) {
            return;
        }
        var body = ev.target && ev.target.closest ? ev.target.closest(BODY_SEL) : null;
        if (!body) {
            return;
        }
        ev.preventDefault();
        var card = dragged;
        clearDropHints();
        if (place(card, body)) {
            publish();
        }
        card.focus({ preventScroll: true });
    });

    /* Keyboard fallback: focus a card, move it with the arrow keys. */
    document.addEventListener("keydown", function (ev) {
        if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") {
            return;
        }
        var card = ev.target && ev.target.closest ? ev.target.closest(CARD_SEL) : null;
        var root = board();
        if (!card || !root || !root.contains(card)) {
            return;
        }
        var bodies = Array.prototype.slice.call(root.querySelectorAll(BODY_SEL));
        var idx = bodies.indexOf(card.closest(BODY_SEL));
        if (idx < 0) {
            return;
        }
        var next = bodies[idx + (ev.key === "ArrowRight" ? 1 : -1)];
        if (!next) {
            return;
        }
        ev.preventDefault();
        if (place(card, next)) {
            publish();
        }
        card.focus({ preventScroll: true });
    });
})();
