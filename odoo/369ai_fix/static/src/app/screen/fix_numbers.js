/** @odoo-module **/
// On every 369ai_fix screen (green screens, their pop-ups, the Booking Desk, My Visits): a number
// box selects what is in it when it is tapped or tabbed into, so typing replaces the value
// instead of adding to it ("3" + "5" = "35").

const SCREENS = ".o_fxs, .o_fxd, .fxp-layer";

document.addEventListener("focusin", (ev) => {
    const el = ev.target;
    if (el instanceof HTMLInputElement && el.type === "number" && el.closest(SCREENS)) {
        // after the click has placed the cursor, or the selection is undone at once
        setTimeout(() => el.select());
    }
});
