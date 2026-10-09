/** @odoo-module **/

/**
 * The website-booking alarm on every page of Odoo.
 *
 * A service, so it lives as long as the web client: somebody working in
 * Invoicing still hears that a customer has booked. It asks the server every
 * 20 seconds and also the moment the bus says something changed, and rings
 * while any booking is still New. Accepting one anywhere - another screen,
 * another tab, the WhatsApp poll - silences it on the next refresh.
 */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { BookingAlarm, presence } from "./booking_shared";

const POLL_MS = 20000;
const MAX_FAILURES = 3;

export const bookingAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const alarm = new BookingAlarm();
        let armed = false;
        let failures = 0;
        let state = null;
        let timer = null;
        let closeNotification = null;
        let poller = null;

        // Browsers only allow sound after a click or key press, so arm on the
        // first one anywhere in the app.
        const arm = async () => {
            if (armed) {
                return;
            }
            armed = await alarm.arm();
            if (armed) {
                document.removeEventListener("pointerdown", arm, true);
                document.removeEventListener("keydown", arm, true);
                sync();
            }
        };
        document.addEventListener("pointerdown", arm, true);
        document.addEventListener("keydown", arm, true);

        function stop() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
            alarm.stop();
        }

        function sync() {
            if (!state || !armed || presence.screens > 0 || !state.new) {
                stop();
                return;
            }
            if (!timer) {
                alarm.ring(state.ring);
                timer = setInterval(() => alarm.ring(state.ring),
                                    (state.ring + state.repeat) * 1000);
            }
        }

        function tellThem() {
            if (!state || !state.new) {
                if (closeNotification) {
                    closeNotification();
                    closeNotification = null;
                }
                return;
            }
            if (closeNotification || presence.screens > 0) {
                return;
            }
            closeNotification = notification.add(
                state.new === 1
                    ? _t("1 new repair booking from the website")
                    : _t("%s new repair bookings from the website", state.new),
                {
                    title: _t("Website booking"),
                    type: "warning",
                    sticky: true,
                    buttons: [{
                        name: _t("Open Live Screen"),
                        primary: true,
                        onClick: () => action.doAction(
                            "danatfix_repair_booking.action_danatfix_booking_screen"),
                    }],
                    onClose: () => {
                        closeNotification = null;
                    },
                });
        }

        async function poll() {
            try {
                state = await orm.call("danatfix.booking", "alarm_state", []);
                failures = 0;
            } catch {
                // No access, or the server is restarting: not worth a dialog.
                failures += 1;
                if (failures >= MAX_FAILURES) {
                    stop();
                    clearInterval(poller);
                }
                return;
            }
            sync();
            tellThem();
        }

        bus_service.addChannel("danatfix_booking");
        bus_service.subscribe("danatfix_booking/refresh", () => poll());
        poller = setInterval(poll, POLL_MS);
        poll();

        return { poll, sync };
    },
};

registry.category("services").add("danatfix_booking_alarm", bookingAlarmService);
