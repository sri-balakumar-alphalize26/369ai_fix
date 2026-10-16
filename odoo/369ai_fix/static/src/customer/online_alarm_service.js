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
import { AlarmLoop, FixAlarm, ORDER_TONE, deskIsOpen } from "@369ai_fix/app/desk/desk_alarm";

const POLL_MS = 20000;
const MAX_FAILURES = 3;
const RING_SECONDS = 6;
const PAUSE_SECONDS = 8;

export const onlineServiceAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const alarm = new FixAlarm();
        const loop = new AlarmLoop(alarm, ORDER_TONE);
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

        function sync() {
            if (!state || !state.count || !armed || deskIsOpen()) {
                loop.stop();
                return;
            }
            loop.start(RING_SECONDS, PAUSE_SECONDS);
        }

        async function openOrder(id) {
            try {
                await orm.call("online.service.order", "action_mark_opened", [[id]]);
            } catch {
                // opening still works below
            }
            await action.doAction({
                type: "ir.actions.act_window",
                res_model: "online.service.order",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
            poll();
        }

        function tellThem() {
            const key = state && state.count && !deskIsOpen() ? state.orders.map((o) => o.id).join(",") : "";
            if (key === shownFor) {
                return;
            }
            if (closeNotification) {
                closeNotification();
                closeNotification = null;
            }
            shownFor = key;
            if (!key) {
                return;
            }
            const first = state.orders[0];
            const text = state.count === 1
                ? _t("%(mode)s order %(name)s from %(customer)s",
                     { mode: first.mode, name: first.name, customer: first.customer })
                : _t("%(count)s new website orders - the oldest waiting is %(name)s",
                     { count: state.count, name: state.orders[state.orders.length - 1].name });
            closeNotification = notification.add(text, {
                title: _t("New website order"),
                type: "warning",
                sticky: true,
                buttons: [{
                    name: _t("Open"),
                    primary: true,
                    onClick: () => openOrder(state.count === 1
                        ? first.id : state.orders[state.orders.length - 1].id),
                }],
                onClose: () => {
                    closeNotification = null;
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
                    clearInterval(poller);
                }
                return;
            }
            sync();
            tellThem();
        }

        bus_service.subscribe("online_service/refresh", () => poll());
        // the Booking Desk opened or closed in this tab: hand the sound over / take it back
        document.addEventListener("fix_desk_presence", () => {
            sync();
            tellThem();
        });
        poller = setInterval(poll, POLL_MS);
        poll();

        return { poll };
    },
};

registry.category("services").add("online_service_alarm", onlineServiceAlarmService);
