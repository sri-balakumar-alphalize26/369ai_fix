/** @odoo-module **/

/**
 * Online Service alarm: rings on every Odoo page while a website order is New
 * and nobody has opened it yet.
 *
 * A service, so it lives as long as the web client. It asks the server every
 * 20 seconds, and at once when the server pushes "online_service/refresh"
 * (a new order, or one was opened/confirmed). The tone (two-tone siren, see
 * app/desk/desk_alarm.js) is different from the Store's, so staff can tell
 * them apart. While the Booking Desk is open in this tab, the desk owns the
 * sound and this service stays quiet.
 */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { AlarmLoop, FixAlarm, ORDER_TONE, SLOT_TONE, alarmBody, alarmTray, deskIsOpen } from "@369ai_fix/app/desk/desk_alarm";

const POLL_MS = 20000;
const MAX_FAILURES = 3;
const RING_SECONDS = 6;
const PAUSE_SECONDS = 8;

export const onlineServiceAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const alarm = new FixAlarm();
        const loop = new AlarmLoop(alarm, ORDER_TONE);
        // a technician waiting at a door for the office's answer about a part: its own card and tone
        const askLoop = new AlarmLoop(alarm, SLOT_TONE);
        let closeAsk = null;
        let askShownFor = "";
        let askQuiet = false;
        let armed = false;
        let failures = 0;
        let state = null;
        let poller = null;
        let closeNotification = null;
        let shownFor = "";

        // Browsers only allow sound after a click or key press: arm on the first one.
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

        const asks = () => (state && state.asks) || [];

        function sync() {
            const quietHere = !armed || deskIsOpen();     // the Booking Desk rings for both itself
            const orders = !!(state && state.count) && !quietHere;
            if (orders) {
                loop.start(RING_SECONDS, PAUSE_SECONDS);
            } else {
                loop.stop();
            }
            if (asks().length && !quietHere) {
                // half a cycle later, so the two tones never sound together
                askLoop.start(RING_SECONDS, PAUSE_SECONDS, orders ? ((RING_SECONDS + PAUSE_SECONDS) * 1000) / 2 : 0);
            } else {
                askLoop.stop();
            }
        }

        /** "Technician waiting for a part": Open goes to that booking on the Booking Desk. */
        function tellAsks() {
            const list = asks();
            const key = list.length && !deskIsOpen() ? list.map((a) => a.id).join(",") : "";
            if (key === askShownFor) {
                return;
            }
            if (closeAsk) {
                askQuiet = true;
                closeAsk();
                askQuiet = false;
                closeAsk = null;
            }
            askShownFor = key;
            alarmTray.drop("ask");
            if (!key) {
                return;
            }
            const first = list[0];
            const text = list.length === 1
                ? _t("%(tech)s asks for %(part)s (%(order)s) and is waiting at the door.",
                     { tech: first.technician || _t("The technician"), part: first.part, order: first.order })
                : _t("%(count)s technicians are waiting for a part - the first: %(part)s (%(order)s).",
                     { count: list.length, part: first.part, order: first.order });
            closeAsk = notification.add(alarmBody("fa-cogs", _t("Technician waiting for a part"), text), {
                title: false,
                type: "warning",
                className: "fx-alarm fx-alarm-slot",
                sticky: true,
                buttons: [{
                    name: _t("Open"),
                    icon: "fa-external-link",
                    primary: true,
                    onClick: async () => {
                        await action.doAction("369ai_fix.action_fix_desk",
                                              { additionalContext: { fix_desk_order_id: first.order_id } });
                        poll();
                    },
                }],
                onClose: () => {
                    closeAsk = null;
                    if (!askQuiet) {
                        alarmTray.hide("ask", key, () => { askShownFor = ""; tellAsks(); });
                    }
                },
            });
        }

        async function openOrder(id) {
            try {
                await orm.call("online.service.order", "action_mark_opened", [[id]]);
            } catch {
                // opening still works below
            }
            // the booking on the Booking Desk (the green screen), not Odoo's form
            await action.doAction("369ai_fix.action_fix_desk", { additionalContext: { fix_desk_order_id: id } });
            poll();
        }

        // X on the pop-up tucks it into the tray (desk_alarm.js); closing it from here does not
        let quiet = false;

        function tellThem() {
            const key = state && state.count && !deskIsOpen() ? state.orders.map((o) => o.id).join(",") : "";
            if (key === shownFor) {
                return;
            }
            if (closeNotification) {
                quiet = true;
                closeNotification();
                quiet = false;
                closeNotification = null;
            }
            shownFor = key;
            alarmTray.drop("order");   // another order (or none): the new state shows by itself
            if (!key) {
                return;
            }
            const first = state.orders[0];
            const text = state.count === 1
                ? _t("%(mode)s order %(name)s from %(customer)s",
                     { mode: first.mode, name: first.name, customer: first.customer })
                : _t("%(count)s new website orders - the oldest waiting is %(name)s",
                     { count: state.count, name: state.orders[state.orders.length - 1].name });
            closeNotification = notification.add(alarmBody("fa-shopping-bag", _t("New website order"), text), {
                title: false,
                type: "warning",
                className: "fx-alarm",
                sticky: true,
                buttons: [{
                    name: _t("Open"),
                    icon: "fa-external-link",
                    primary: true,
                    onClick: () => openOrder(state.count === 1
                        ? first.id : state.orders[state.orders.length - 1].id),
                }],
                onClose: () => {
                    closeNotification = null;
                    if (!quiet) {
                        alarmTray.hide("order", key, () => { shownFor = ""; tellThem(); });
                    }
                },
            });
        }

        async function poll() {
            try {
                state = await orm.silent.call("online.service.order", "alarm_state", []);
                failures = 0;
            } catch {
                // No access, or the server is restarting: not worth a dialog.
                failures += 1;
                if (failures >= MAX_FAILURES) {
                    loop.stop();
                    askLoop.stop();
                    clearInterval(poller);
                }
                return;
            }
            sync();
            tellThem();
            tellAsks();
        }

        bus_service.subscribe("online_service/refresh", () => poll());
        // the Booking Desk opened or closed in this tab: hand the sound over / take it back
        document.addEventListener("fix_desk_presence", () => {
            sync();
            tellThem();
            tellAsks();
        });
        poller = setInterval(poll, POLL_MS);
        poll();

        return { poll };
    },
};

registry.category("services").add("online_service_alarm", onlineServiceAlarmService);
