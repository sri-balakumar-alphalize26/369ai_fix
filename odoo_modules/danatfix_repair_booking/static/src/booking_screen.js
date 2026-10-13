/** @odoo-module **/

/**
 * Store > Website Bookings > Live Screen.
 *
 * A card for every website booking waiting for review, oldest first, and for
 * every visit time a customer has just booked. Two alarms ring while the screen
 * is open: the chime for a booking to review, a lower tone for a booked time.
 * Redraws when the bus says so (a booking arrived, somebody tapped the WhatsApp
 * poll, a customer booked a time) and every 20 s besides.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { BookingAlarm, SLOT_TONE, presence } from "./booking_shared";

const REFRESH_MS = 20000;
const MODEL = "online.service.order";

export class BookingScreen extends Component {
    static template = "danatfix_repair_booking.BookingScreen";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        this.action = useService("action");
        this.background = useService("danatfix_booking_alarm");
        this.alarm = new BookingAlarm();
        this.slotAlarm = new BookingAlarm();
        this.state = useState({
            rows: [],
            newCount: 0,
            slotCount: 0,
            ring: 20,
            repeat: 15,
            pollReady: false,
            soundOn: false,
            loading: true,
            busy: 0,
            now: Date.now(),
        });
        this._timer = null;
        this._slotTimer = null;
        this._onBus = () => this.refresh();

        onWillStart(async () => {
            // This screen owns the sound now: quiet the background copy at once.
            presence.screens += 1;
            this.background.sync();
            this.state.soundOn = (await this.alarm.arm()) && (await this.slotAlarm.arm());
            await this.refresh();
            this.bus.addChannel("danatfix_booking");
            this.bus.subscribe("danatfix_booking/refresh", this._onBus);
            this._poller = setInterval(() => this.refresh(), REFRESH_MS);
            this._clock = setInterval(() => (this.state.now = Date.now()), 30000);
        });

        onWillUnmount(() => {
            presence.screens = Math.max(0, presence.screens - 1);
            this._stopAlarms();
            clearInterval(this._poller);
            clearInterval(this._clock);
            this.bus.unsubscribe("danatfix_booking/refresh", this._onBus);
            // Hand the sound back to the background service.
            this.background.poll();
        });
    }

    _apply(data) {
        this.state.rows = data.rows;
        this.state.newCount = data.new;
        this.state.slotCount = data.slots;
        this.state.pollReady = data.poll_ready;
        if (data.ring !== this.state.ring || data.repeat !== this.state.repeat) {
            this.state.ring = data.ring;
            this.state.repeat = data.repeat;
            this._stopAlarms();
        }
        this.state.loading = false;
        this.state.now = Date.now();
        this._syncAlarms();
        if (data.warning) {
            this.notification.add(data.warning, { type: "warning" });
        }
    }

    async refresh() {
        try {
            this._apply(await this.orm.call(MODEL, "desk_screen_data", []));
        } catch {
            // Server restarting: the next refresh will catch up.
        }
    }

    _syncAlarms() {
        const waiting = this.state.rows.filter((r) => r.stage === "new").length;
        const cycle = (this.state.ring + this.state.repeat) * 1000;
        if (waiting > 0 && this.state.soundOn) {
            if (!this._timer) {
                this.alarm.ring(this.state.ring);
                this._timer = setInterval(() => this.alarm.ring(this.state.ring), cycle);
            }
        } else if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
            this.alarm.stop();
        }
        if (this.state.slotCount > 0 && this.state.soundOn) {
            if (!this._slotTimer) {
                this.slotAlarm.ring(this.state.ring, SLOT_TONE);
                this._slotTimer = setInterval(() => this.slotAlarm.ring(this.state.ring, SLOT_TONE), cycle);
            }
        } else if (this._slotTimer) {
            clearInterval(this._slotTimer);
            this._slotTimer = null;
            this.slotAlarm.stop();
        }
    }

    _stopAlarms() {
        for (const name of ["_timer", "_slotTimer"]) {
            if (this[name]) {
                clearInterval(this[name]);
                this[name] = null;
            }
        }
        this.alarm.stop();
        this.slotAlarm.stop();
    }

    async onEnableSound() {
        if ((await this.alarm.arm()) && (await this.slotAlarm.arm())) {
            this.state.soundOn = true;
            this.alarm.ring(2);
            this._syncAlarms();
        } else {
            this.notification.add(
                "This browser will not play sound here. Check the tab is not muted and the volume is up.",
                { type: "warning" });
        }
    }

    onTestSound() {
        if (!this._timer && !this._slotTimer) {
            this.alarm.ring(2);
            setTimeout(() => this.slotAlarm.ring(2, SLOT_TONE), 2500);
        }
    }

    async act(row, what) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = row.id;
        try {
            const res = await this.orm.call(MODEL, "desk_act", [[row.id], what]);
            if (res && res.action) {
                await this.action.doAction(res.action, { onClose: () => this.refresh() });
            } else {
                this._apply(res);
            }
        } finally {
            this.state.busy = 0;
        }
    }

    openOrder(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openJobCard(card) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "job.card",
            res_id: card.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openList() {
        this.action.doAction("369ai_fix_customer_module.action_online_order_all");
    }

    age(row) {
        const created = new Date(row.created.replace(" ", "T") + "Z").getTime();
        const minutes = Math.max(0, Math.floor((this.state.now - created) / 60000));
        if (minutes < 1) {
            return "just now";
        }
        if (minutes < 60) {
            return `${minutes} min ago`;
        }
        const hours = Math.floor(minutes / 60);
        return hours < 24 ? `${hours} h ${minutes % 60} min ago` : `${Math.floor(hours / 24)} d ago`;
    }

    stageLabel(row) {
        return {
            new: "To review",
            calling: "Calling customer",
            reject: "Reject - reason needed",
            slot: "Visit time booked",
        }[row.stage] || row.stage;
    }

    where(row) {
        return [row.address, row.area].filter(Boolean).join(", ");
    }

    lineLabel(line) {
        const what = [line.device, line.model].filter(Boolean).join(" ");
        return what ? `${what} — ${line.issue}` : line.issue;
    }

    money(row, amount) {
        return amount === null || amount === undefined ? "" : `${row.currency} ${Number(amount).toFixed(3)}`;
    }
}

registry.category("actions").add("danatfix_repair_booking.screen", BookingScreen);
