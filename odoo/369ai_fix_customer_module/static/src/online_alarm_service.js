/** @odoo-module **/

/**
 * Online Service alarm: rings on every Odoo page while a website order is New
 * and nobody has opened it yet.
 *
 * A service, so it lives as long as the web client. It asks the server every
 * 20 seconds, and at once when the server pushes "online_service/refresh"
 * (a new order, or one was opened/confirmed). Web Audio, no sound file. Same
 * design as the Store's alarm, kept as this module's own copy so nothing
 * here depends on another module's JavaScript. The tone (two-tone siren) is
 * different from the Store's, so staff can tell them apart.
 */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const POLL_MS = 20000;
const MAX_FAILURES = 3;
const RING_SECONDS = 6;
const PAUSE_SECONDS = 8;

class OnlineAlarm {
    constructor() {
        this.ctx = null;
        this.armed = false;
        this._timer = null;
    }

    async arm() {
        if (this.armed) {
            return true;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) {
            return false;
        }
        this.ctx = this.ctx || new Ctx();
        try {
            await this.ctx.resume();
        } catch {
            // the state below tells the truth
        }
        this.armed = this.ctx.state === "running";
        return this.armed;
    }

    _tone(freq, at, length) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "triangle";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.8, at + 0.02);
        gain.gain.setValueAtTime(0.8, at + length - 0.04);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(at);
        osc.stop(at + length + 0.02);
    }

    /** Two-tone siren for `seconds`, scheduled one second ahead so stop() is instant. */
    ring(seconds) {
        this.stop();
        if (!this.armed || !this.ctx) {
            return;
        }
        const notes = [880, 660];
        const end = this.ctx.currentTime + seconds;
        let next = this.ctx.currentTime + 0.05;
        let i = 0;
        const schedule = () => {
            const horizon = this.ctx.currentTime + 1.0;
            while (next < horizon && next < end) {
                this._tone(notes[i % 2], next, 0.32);
                i += 1;
                next += 0.36;
            }
            if (next >= end) {
                this.stop();
            }
        };
        schedule();
        this._timer = setInterval(schedule, 400);
    }

    stop() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }
}

export const onlineServiceAlarmService = {
    dependencies: ["orm", "bus_service", "notification", "action"],

    start(env, { orm, bus_service, notification, action }) {
        const alarm = new OnlineAlarm();
        let armed = false;
        let failures = 0;
        let state = null;
        let repeat = null;
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

        function stop() {
            if (repeat) {
                clearInterval(repeat);
                repeat = null;
            }
            alarm.stop();
        }

        function sync() {
            if (!state || !state.count || !armed) {
                stop();
                return;
            }
            if (!repeat) {
                alarm.ring(RING_SECONDS);
                repeat = setInterval(() => alarm.ring(RING_SECONDS),
                                     (RING_SECONDS + PAUSE_SECONDS) * 1000);
            }
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
            const key = state && state.count ? state.orders.map((o) => o.id).join(",") : "";
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
                    stop();
                    clearInterval(poller);
                }
                return;
            }
            sync();
            tellThem();
        }

        bus_service.subscribe("online_service/refresh", () => poll());
        poller = setInterval(poll, POLL_MS);
        poll();

        return { poll };
    },
};

registry.category("services").add("online_service_alarm", onlineServiceAlarmService);
