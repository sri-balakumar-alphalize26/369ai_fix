/** @odoo-module **/

/**
 * Store > Website Bookings > Live Screen.
 *
 * Cards for every booking still open, oldest first, and an alarm that rings
 * while any of them is New. Redraws when the bus says so (a booking arrived,
 * somebody tapped the WhatsApp poll) and every 20 s besides.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { BookingAlarm, presence } from "./booking_shared";

const REFRESH_MS = 20000;

export class BookingScreen extends Component {
    static template = "danatfix_repair_booking.BookingScreen";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.background = useService("danatfix_booking_alarm");
        this.alarm = new BookingAlarm();
        this.state = useState({
            rows: [],
            newCount: 0,
            ring: 20,
            repeat: 15,
            pollReady: false,
            soundOn: false,
            loading: true,
            busy: 0,
            now: Date.now(),
        });
        this._timer = null;
        this._onBus = () => this.refresh();

        onWillStart(async () => {
            // This screen owns the sound now: quiet the background copy at once.
            presence.screens += 1;
            this.background.sync();
            // Already allowed to play in this tab (the user clicked somewhere
            // before opening the screen)? Then the alarm is on from the start.
            this.state.soundOn = await this.alarm.arm();
            await this.refresh();
            this.bus.addChannel("danatfix_booking");
            this.bus.subscribe("danatfix_booking/refresh", this._onBus);
            this._poller = setInterval(() => this.refresh(), REFRESH_MS);
            this._clock = setInterval(() => (this.state.now = Date.now()), 30000);
        });

        onWillUnmount(() => {
            presence.screens = Math.max(0, presence.screens - 1);
            this._stopAlarm();
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
        this.state.pollReady = data.poll_ready;
        if (data.ring !== this.state.ring || data.repeat !== this.state.repeat) {
            this.state.ring = data.ring;
            this.state.repeat = data.repeat;
            this._stopAlarm();
        }
        this.state.loading = false;
        this.state.now = Date.now();
        this._syncAlarm();
        if (data.warning) {
            this.notification.add(data.warning, { type: "warning" });
        }
    }

    async refresh() {
        try {
            this._apply(await this.orm.call("danatfix.booking", "screen_data", []));
        } catch {
            // Server restarting: the next refresh will catch up.
        }
    }

    _syncAlarm() {
        if (this.state.newCount > 0 && this.state.soundOn) {
            if (!this._timer) {
                this.alarm.ring(this.state.ring);
                this._timer = setInterval(() => this.alarm.ring(this.state.ring),
                                          (this.state.ring + this.state.repeat) * 1000);
            }
        } else {
            this._stopAlarm();
        }
    }

    _stopAlarm() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
        this.alarm.stop();
    }

    async onEnableSound() {
        if (await this.alarm.arm()) {
            this.state.soundOn = true;
            this.alarm.ring(2);
            this._syncAlarm();
        } else {
            this.notification.add(
                "This browser will not play sound here. Check the tab is not muted and the volume is up.",
                { type: "warning" });
        }
    }

    onTestSound() {
        if (!this._timer) {
            this.alarm.ring(3);
        }
    }

    async act(row, action) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = row.id;
        try {
            this._apply(await this.orm.call("danatfix.booking", "screen_act", [[row.id], action]));
        } finally {
            this.state.busy = 0;
        }
    }

    onCancel(row) {
        this.dialog.add(ConfirmationDialog, {
            title: `Cancel ${row.name}?`,
            body: row.poll_sent
                ? "The staff WhatsApp group is told it was cancelled. The customer is not messaged - tell them yourself if needed."
                : "The customer is not messaged - tell them yourself if needed.",
            confirmLabel: "Cancel the booking",
            cancelLabel: "Keep it",
            confirm: () => this.act(row, "cancel"),
        });
    }

    openRecord(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "danatfix.booking",
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openList() {
        this.action.doAction("danatfix_repair_booking.action_danatfix_booking_list");
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
        return { new: "New", calling: "Calling customer", accepted: "Accepted" }[row.state] || row.state;
    }

    where(row) {
        return [row.address, row.area].filter(Boolean).join(", ");
    }

    lineLabel(line) {
        const what = [line.device, line.model].filter(Boolean).join(" ");
        return what ? `${what} — ${line.issue}` : line.issue;
    }
}

registry.category("actions").add("danatfix_repair_booking.screen", BookingScreen);
