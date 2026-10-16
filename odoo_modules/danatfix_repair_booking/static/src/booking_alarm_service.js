/** @odoo-module **/

/**
 * The two website-booking alarms on every page of Odoo.
 *
 *  1. New booking: the chime, while any website order waits for review
 *     (approve / reject) and nobody is calling the customer about it.
 *  2. Visit time booked: a lower "ding-dong", while a customer has booked the
 *     visit time and nobody has pressed Seen.
 *
 * A service, so it lives as long as the web client. It asks the server every
 * 20 seconds and at once when the bus says something changed. While the Booking
 * Desk of the 369 ai Fix app (or the old Live Screen) is open in this tab, that
 * screen owns the sound (see `presence` and `deskIsOpen`).
 */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { BookingAlarm, SLOT_TONE, presence } from "./booking_shared";
import { deskIsOpen } from "@369ai_fix/app/desk/desk_alarm";

const POLL_MS = 20000;
const MAX_FAILURES = 3;

export const bookingAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const newAlarm = new BookingAlarm();
        const slotAlarm = new BookingAlarm();
        let armed = false;
        let failures = 0;
        let state = null;
        let newTimer = null;
        let slotTimer = null;
        let closeNew = null;
        let closeSlot = null;
        let slotKey = "";
        let poller = null;

        // Browsers only allow sound after a click or key press, so arm on the
        // first one anywhere in the app.
        const arm = async () => {
            if (armed) {
                return;
            }
            armed = (await newAlarm.arm()) && (await slotAlarm.arm());
            if (armed) {
                document.removeEventListener("pointerdown", arm, true);
                document.removeEventListener("keydown", arm, true);
                sync();
            }
        };
        document.addEventListener("pointerdown", arm, true);
        document.addEventListener("keydown", arm, true);

        function stopNew() {
            if (newTimer) {
                clearInterval(newTimer);
                newTimer = null;
            }
            newAlarm.stop();
        }

        function stopSlot() {
            if (slotTimer) {
                clearInterval(slotTimer);
                slotTimer = null;
            }
            slotAlarm.stop();
        }

        const screenOpen = () => presence.screens > 0 || deskIsOpen();

        function sync() {
            if (!state || !armed || screenOpen()) {
                stopNew();
                stopSlot();
                return;
            }
            if (state.new) {
                if (!newTimer) {
                    newAlarm.ring(state.ring);
                    newTimer = setInterval(() => newAlarm.ring(state.ring),
                                           (state.ring + state.repeat) * 1000);
                }
            } else {
                stopNew();
            }
            if (state.slots.length) {
                if (!slotTimer) {
                    // Offset by half a cycle so the two alarms never sound together.
                    const cycle = (state.ring + state.repeat) * 1000;
                    setTimeout(() => {
                        if (state.slots.length && !screenOpen()) {
                            slotAlarm.ring(state.ring, SLOT_TONE);
                        }
                    }, state.new ? cycle / 2 : 0);
                    slotTimer = setInterval(() => slotAlarm.ring(state.ring, SLOT_TONE), cycle);
                }
            } else {
                stopSlot();
            }
        }

        // "Open" goes to the Booking Desk, which has the Live Screen's cards and the rest of the flow.
        const openScreen = () => action.doAction("369ai_fix.action_fix_desk");

        async function seen(id) {
            try {
                await orm.call("online.service.order", "action_wb_slot_seen", [[id]]);
            } catch {
                // the screen can still do it
            }
            poll();
        }

        function tellThem() {
            // New bookings
            if (!state.new) {
                if (closeNew) {
                    closeNew();
                    closeNew = null;
                }
            } else if (!closeNew && !screenOpen()) {
                closeNew = notification.add(
                    state.new === 1
                        ? _t("1 new website booking to review")
                        : _t("%s new website bookings to review", state.new),
                    {
                        title: _t("Website booking"),
                        type: "warning",
                        sticky: true,
                        buttons: [{ name: _t("Open Booking Desk"), primary: true, onClick: openScreen }],
                        onClose: () => {
                            closeNew = null;
                        },
                    });
            }
            // Visit times booked
            const key = state.slots.map((s) => s.id).join(",");
            if (key !== slotKey || !key) {
                if (closeSlot) {
                    closeSlot();
                    closeSlot = null;
                }
                slotKey = key;
            }
            if (key && !closeSlot && !screenOpen()) {
                const first = state.slots[0];
                closeSlot = notification.add(
                    state.slots.length === 1
                        ? _t("%(name)s - %(customer)s booked %(slot)s",
                             { name: first.name, customer: first.customer, slot: first.slot })
                        : _t("%s customers booked their visit time", state.slots.length),
                    {
                        title: _t("Visit time booked"),
                        type: "info",
                        sticky: true,
                        buttons: [
                            state.slots.length === 1
                                ? { name: _t("Seen"), primary: true, onClick: () => seen(first.id) }
                                : { name: _t("Open Booking Desk"), primary: true, onClick: openScreen },
                        ],
                        onClose: () => {
                            closeSlot = null;
                        },
                    });
            }
        }

        async function poll() {
            try {
                state = await orm.silent.call("online.service.order", "desk_alarm_state", []);
                failures = 0;
            } catch {
                // No access, or the server is restarting: not worth a dialog.
                failures += 1;
                if (failures >= MAX_FAILURES) {
                    stopNew();
                    stopSlot();
                    clearInterval(poller);
                }
                return;
            }
            sync();
            tellThem();
        }

        bus_service.addChannel("danatfix_booking");
        bus_service.subscribe("danatfix_booking/refresh", () => poll());
        bus_service.subscribe("online_service/refresh", () => poll());
        // the Booking Desk opened or closed in this tab: hand the sound over / take it back
        document.addEventListener("fix_desk_presence", () => {
            sync();
            if (state) {
                tellThem();
            }
        });
        poller = setInterval(poll, POLL_MS);
        poll();

        return { poll, sync };
    },
};

registry.category("services").add("danatfix_booking_alarm", bookingAlarmService);
