/** @odoo-module **/

/**
 * The Booking Desk: one screen that carries a website booking from new to done.
 *
 *  rail (one stage per booking)  |  the cards of that stage  |  the booking: buttons,
 *  new · calling · time to book  |  oldest first              |  customer, repairs, parts,
 *  · time booked · to assign     |                            |  words & photos, visit
 *  · assigned · live · working   |                            |  timeline, technician,
 *  · done today · rejected       |                            |  live map
 *
 * Both alarms ring here while the desk is open (a chime for a booking to review,
 * a lower ding-dong for a booked time); the background services stay quiet
 * meanwhile (see desk_alarm.js). Redraws when the bus says something changed and
 * every 20 s besides; the server answers "nothing changed" cheaply (`since`).
 */

import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { AlarmLoop, FixAlarm, NEW_TONE, SLOT_TONE, setDeskOpen } from "./desk_alarm";
import { destroyMap, hasLeaflet, mountMap, updateMap } from "./leaflet_map";

const MODEL = "online.service.order";
const POLL_MS = 20000;
const PRESENCE_EVENT = "fix_desk_presence";

// What each stage means, under its title.
const HINTS = {
    new: "Website bookings waiting for a decision: approve, call the customer or reject.",
    calling: "Somebody is on the phone with the customer.",
    approved: "Approved; the customer has the estimate and a link to pick a time.",
    booked: "The customer picked a time. Press Seen so the ding-dong stops.",
    to_assign: "Time booked and seen: choose the technician and send them the link.",
    assigned: "The technician has the link; waiting for them to set off.",
    live: "On the way or at the door: the map follows the technician's phone.",
    working: "Repair in progress (at the door or at the office).",
    done_today: "Visits finished today.",
    rejected: "Rejected today, with the reason sent to the customer.",
};

const BUTTONS = {
    approve: { label: "Approve", kind: "primary", icon: "fa-check" },
    call: { label: "Call", kind: "ghost", icon: "fa-phone" },
    reject: { label: "Reject", kind: "danger-ghost", icon: "fa-times" },
    seen: { label: "Seen", kind: "primary", icon: "fa-eye" },
    assign: { label: "Assign & send link", kind: "primary", icon: "fa-user-plus" },
    send_link: { label: "Send link again", kind: "ghost", icon: "fa-whatsapp" },
    on_the_way: { label: "On the way", kind: "primary", icon: "fa-car" },
    arrived: { label: "Arrived", kind: "primary", icon: "fa-map-marker" },
    arrived_skip: { label: "Arrived, no code", kind: "ghost", icon: "fa-map-marker" },
    start: { label: "Start work", kind: "primary", icon: "fa-wrench" },
    done: { label: "Done", kind: "primary", icon: "fa-check-circle" },
    office: { label: "Take to the office", kind: "ghost", icon: "fa-building" },
    cancel_visit: { label: "Cancel visit", kind: "danger-ghost", icon: "fa-ban" },
};

export class FixDesk extends Component {
    static template = "369ai_fix.Desk";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        this.state = useState({
            loading: true,
            stage: "new",
            stages: [],
            counts: {},
            rows: [],
            since: "",
            technicians: [],
            ring: 20,
            repeat: 15,
            pollReady: false,
            hasCalling: false,
            soundOn: false,
            busy: 0,
            now: Date.now(),
            selectedId: 0,
            detail: null,
            detailLoading: false,
            showDetail: false,
            techPick: 0,
            askCancel: false,
            cancelReason: "",
        });
        this.newAlarm = new FixAlarm();
        this.slotAlarm = new FixAlarm();
        this.newLoop = new AlarmLoop(this.newAlarm, NEW_TONE);
        this.slotLoop = new AlarmLoop(this.slotAlarm, SLOT_TONE);
        this.mapHandle = null;
        this.mapEl = null;
        this._onBus = () => this.load();

        onWillStart(async () => {
            setDeskOpen(true);
            document.dispatchEvent(new CustomEvent(PRESENCE_EVENT));
            this.state.soundOn = (await this.newAlarm.arm()) && (await this.slotAlarm.arm());
            await this.load({ force: true });
        });
        onMounted(() => {
            this.bus.addChannel("fix_desk");
            this.bus.subscribe("fix_desk/refresh", this._onBus);
            this.bus.subscribe("danatfix_booking/refresh", this._onBus);
            this.bus.subscribe("online_service/refresh", this._onBus);
            this._poller = setInterval(() => this.load(), POLL_MS);
            this._clock = setInterval(() => (this.state.now = Date.now()), 30000);
        });
        onWillUnmount(() => {
            setDeskOpen(false);
            this.newLoop.stop();
            this.slotLoop.stop();
            clearInterval(this._poller);
            clearInterval(this._clock);
            this.bus.unsubscribe("fix_desk/refresh", this._onBus);
            this.bus.unsubscribe("danatfix_booking/refresh", this._onBus);
            this.bus.unsubscribe("online_service/refresh", this._onBus);
            destroyMap(this.mapHandle);
            this.mapHandle = null;
            document.dispatchEvent(new CustomEvent(PRESENCE_EVENT));
        });
        // the map follows the detail pane: mounted when its element appears, redrawn on every change
        useEffect(
            () => {
                const el = this.mapRef.el;
                const data = this.state.detail && this.state.detail.map;
                if (!el || !data) {
                    if (this.mapHandle) {
                        destroyMap(this.mapHandle);
                        this.mapHandle = null;
                        this.mapEl = null;
                    }
                    return;
                }
                if (!this.mapHandle || this.mapEl !== el) {
                    destroyMap(this.mapHandle);
                    this.mapHandle = mountMap(el);
                    this.mapEl = el;
                }
                updateMap(this.mapHandle, data);
            },
            () => [this.mapRef.el, this.state.detail && this.state.detail.map, this.state.showDetail]
        );
    }

    // ------------------------------------------------------------------ data
    async load({ force = false } = {}) {
        let data;
        try {
            data = await this.orm.silent.call(MODEL, "fix_desk_load", [], {
                stage: this.state.stage,
                since: force ? null : this.state.since || null,
            });
        } catch {
            return; // server restarting: the next poll catches up
        }
        const changed = this._apply(data);
        if ((changed || force) && this.state.selectedId) {
            this.loadDetail();
        }
    }

    /** Puts a load result in the state; true when the list changed. */
    _apply(data) {
        const s = this.state;
        s.stages = data.stages;
        s.counts = data.counts;
        s.technicians = data.technicians;
        s.pollReady = data.poll_ready;
        s.hasCalling = data.has_calling;
        if (data.ring !== s.ring || data.repeat !== s.repeat) {
            s.ring = data.ring;
            s.repeat = data.repeat;
            this.newLoop.stop();
            this.slotLoop.stop();
        }
        s.now = Date.now();
        s.loading = false;
        this._syncAlarms();
        if (data.warning) {
            this.notification.add(data.warning, { type: "warning" });
        }
        // rows come back only on the first load and when something changed since `since`
        const changed = Array.isArray(data.rows);
        s.since = data.since;
        if (changed) {
            s.rows = data.rows;
            if (s.selectedId && s.detail && !s.rows.some((r) => r.id === s.selectedId)) {
                // the booking moved to another stage: keep its detail, say so
                s.detail.moved = true;
            }
        }
        return changed;
    }

    railClass(s) {
        const on = s.key === this.state.stage ? " fxd-on" : "";
        const has = this.state.counts[s.key] ? " fxd-has" : "";
        return `fxd-rail-btn fxd-stage-${s.key}${on}${has}`;
    }

    cardClass(row) {
        return `fxd-card fxd-stage-${row.stage}${row.id === this.state.selectedId ? " fxd-on" : ""}`;
    }

    where(d) {
        return [d.address, d.area].filter((x) => x).join(", ");
    }

    async loadDetail() {
        const id = this.state.selectedId;
        if (!id) {
            return;
        }
        this.state.detailLoading = true;
        try {
            const detail = await this.orm.silent.call(MODEL, "fix_desk_detail", [[id]]);
            if (this.state.selectedId === id) {
                this.state.detail = detail;
                if (detail.visit && detail.visit.technician_id) {
                    this.state.techPick = detail.visit.technician_id;
                }
            }
        } catch {
            // keeps what it had
        }
        this.state.detailLoading = false;
    }

    setStage(key) {
        if (key === this.state.stage) {
            return;
        }
        this.state.stage = key;
        this.state.rows = [];
        this.state.since = "";
        this.state.loading = true;
        this.closeDetail();
        this.load({ force: true });
    }

    select(row) {
        this.state.selectedId = row.id;
        this.state.showDetail = true;
        this.state.askCancel = false;
        this.state.detail = null;
        this.loadDetail();
    }

    closeDetail() {
        this.state.selectedId = 0;
        this.state.detail = null;
        this.state.showDetail = false;
        this.state.askCancel = false;
    }

    // ------------------------------------------------------------------ buttons
    async act(what, extra = {}) {
        const id = this.state.selectedId;
        if (!id || this.state.busy) {
            return;
        }
        if (what === "assign" && !this.state.techPick) {
            this.notification.add(_t("Choose the technician first."), { type: "warning" });
            return;
        }
        if (what === "cancel_visit" && !this.state.askCancel) {
            this.state.askCancel = true;
            return;
        }
        this.state.busy = id;
        try {
            const kwargs = { stage: this.state.stage, ...extra };
            if (what === "assign") {
                kwargs.technician_id = this.state.techPick;
            }
            if (what === "cancel_visit") {
                kwargs.reason = this.state.cancelReason;
            }
            const res = await this.orm.call(MODEL, "fix_desk_act", [[id], what], kwargs);
            this.state.askCancel = false;
            if (res && res.action) {
                await this.action.doAction(res.action, { onClose: () => this.load({ force: true }) });
                if (res.action.type === "ir.actions.act_url") {
                    this.load({ force: true });
                }
            } else {
                this._apply(res);
                if (res.detail) {
                    this.state.detail = res.detail;
                }
            }
        } finally {
            this.state.busy = 0;
        }
    }

    button(key) {
        const b = BUTTONS[key] || { label: key, kind: "ghost", icon: "fa-circle" };
        const d = this.state.detail || {};
        let label = _t(b.label);
        if (key === "call" && this.state.hasCalling) {
            label = _t("I'm calling");
        } else if (key === "reject" && d.reject_pending) {
            label = _t("Write the reason and reject");
        } else if (key === "assign" && d.visit && d.visit.state === "assigned") {
            label = _t("Change technician");
        } else if (key === "arrived" && d.visit && d.visit.arrival_code) {
            label = _t("Arrived (customer's code)");
        }
        return { ...b, label, kind: key === "reject" && d.reject_pending ? "danger" : b.kind };
    }

    onEnableSound() {
        Promise.all([this.newAlarm.arm(), this.slotAlarm.arm()]).then(([a, b]) => {
            if (a && b) {
                this.state.soundOn = true;
                this.newAlarm.ring(1.5, NEW_TONE);
                this._syncAlarms();
            } else {
                this.notification.add(
                    _t("This browser will not play sound here. Check the tab is not muted and the volume is up."),
                    { type: "warning" });
            }
        });
    }

    onTestSound() {
        if (!this.newLoop.running && !this.slotLoop.running) {
            this.newAlarm.ring(2, NEW_TONE);
            setTimeout(() => this.slotAlarm.ring(2, SLOT_TONE), 2500);
        }
    }

    _syncAlarms() {
        const s = this.state;
        if (!s.soundOn) {
            this.newLoop.stop();
            this.slotLoop.stop();
            return;
        }
        if (s.counts.new > 0) {
            this.newLoop.start(s.ring, s.repeat);
        } else {
            this.newLoop.stop();
        }
        if (s.counts.booked > 0) {
            // half a cycle later, so the two tones never sound together
            this.slotLoop.start(s.ring, s.repeat, s.counts.new > 0 ? ((s.ring + s.repeat) * 1000) / 2 : 0);
        } else {
            this.slotLoop.stop();
        }
    }

    // ------------------------------------------------------------------ open things
    openForm(model, id) {
        if (!id) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAll() {
        this.action.doAction("369ai_fix.action_online_order_all");
    }

    // ------------------------------------------------------------------ words
    stageLabel(key) {
        const found = this.state.stages.find((s) => s.key === key);
        return found ? found.label : key;
    }

    stageHint(key) {
        return _t(HINTS[key] || "");
    }

    age(row) {
        if (!row.created) {
            return "";
        }
        const created = new Date(row.created.replace(" ", "T") + "Z").getTime();
        const minutes = Math.max(0, Math.floor((this.state.now - created) / 60000));
        if (minutes < 1) {
            return _t("just now");
        }
        if (minutes < 60) {
            return _t("%s min", minutes);
        }
        const hours = Math.floor(minutes / 60);
        if (hours < 24) {
            return _t("%(h)s h %(m)s min", { h: hours, m: minutes % 60 });
        }
        return _t("%s d", Math.floor(hours / 24));
    }

    /** "14:05" today, else "Mon 14:05" (the server sends UTC). */
    when(value) {
        if (!value) {
            return "";
        }
        const d = new Date(value.replace(" ", "T") + "Z");
        const now = new Date(this.state.now);
        const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        if (d.toDateString() === now.toDateString()) {
            return time;
        }
        return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) + " " + time;
    }

    money(amount, currency) {
        if (amount === null || amount === undefined) {
            return "";
        }
        return `${currency || ""} ${Number(amount).toFixed(3)}`;
    }

    lineLabel(line) {
        const what = [line.device, line.model].filter(Boolean).join(" ");
        return what ? `${what} — ${line.issue}` : line.issue;
    }

    get hasMap() {
        return hasLeaflet();
    }

    get mapChip() {
        const m = this.state.detail && this.state.detail.map;
        if (!m || !m.tech) {
            return "";
        }
        const parts = [];
        if (m.distance_km) {
            parts.push(_t("%s km", m.distance_km.toFixed(1)));
        }
        if (m.eta_minutes) {
            parts.push(_t("ETA %s min", m.eta_minutes));
        }
        return parts.join(" · ");
    }
}

registry.category("actions").add("369ai_fix_desk", FixDesk);
