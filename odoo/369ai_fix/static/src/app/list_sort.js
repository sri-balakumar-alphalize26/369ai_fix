/** @odoo-module **/

/**
 * The order of a list (the Booking Desk's cards, My Visits): chosen in the list head, kept in
 * this browser. Each option is [key, label, field, direction]; rows without that field go last.
 *
 *   <FixSort options="sorts" value="state.sort" onChange="(key) => this.setSort(key)"/>
 *
 * FixSort is our own menu (the green look), not the browser's dropdown: click or the keyboard
 * (arrows, Enter, Escape) to choose; a click outside closes it.
 */

import { Component, useExternalListener, useRef, useState } from "@odoo/owl";

/** The order chosen before in this browser, else `fallback` (else the first option). */
export function readSort(storageKey, options, fallback = "") {
    let saved = "";
    try {
        saved = window.localStorage.getItem(storageKey) || "";
    } catch {
        // private window / blocked storage: the default
    }
    const known = (key) => options.some((o) => o[0] === key);
    return known(saved) ? saved : known(fallback) ? fallback : options[0][0];
}

export function saveSort(storageKey, value) {
    try {
        window.localStorage.setItem(storageKey, value);
    } catch {
        // not kept: it still applies until the page is left
    }
}

export function sortRows(rows, options, key) {
    const option = options.find((o) => o[0] === key) || options[0];
    const [, , field, direction] = option;
    const sign = direction === "desc" ? -1 : 1;
    const valueOf = typeof field === "function" ? field : (row) => row[field];
    return [...rows].sort((a, b) => {
        const x = valueOf(a) || "";
        const y = valueOf(b) || "";
        if (!x || !y) {
            return x ? -1 : y ? 1 : 0;          // without a date: last, whichever the direction
        }
        return x < y ? -sign : x > y ? sign : 0;
    });
}

export class FixSort extends Component {
    static template = "369ai_fix.FixSort";
    static props = ["options", "value", "onChange"];

    setup() {
        this.root = useRef("root");
        this.state = useState({ open: false, active: 0 });
        useExternalListener(window, "pointerdown", (ev) => {
            if (this.state.open && this.root.el && !this.root.el.contains(ev.target)) {
                this.state.open = false;
            }
        }, { capture: true });
    }

    get current() {
        return this.props.options.find((o) => o[0] === this.props.value) || this.props.options[0];
    }

    get currentIndex() {
        return Math.max(0, this.props.options.findIndex((o) => o[0] === this.props.value));
    }

    toggle() {
        this.state.open = !this.state.open;
        this.state.active = this.currentIndex;
    }

    pick(key) {
        this.state.open = false;
        if (key !== this.props.value) {
            this.props.onChange(key);
        }
    }

    onKey(ev) {
        const n = this.props.options.length;
        if (ev.key === "Escape") {
            this.state.open = false;
        } else if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
            ev.preventDefault();
            if (!this.state.open) {
                this.toggle();
                return;
            }
            this.state.active = (this.state.active + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
        } else if ((ev.key === "Enter" || ev.key === " ") && this.state.open) {
            ev.preventDefault();
            this.pick(this.props.options[this.state.active][0]);
        } else {
            return;
        }
        ev.stopPropagation();
    }
}
