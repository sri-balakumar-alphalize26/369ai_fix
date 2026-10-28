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
import { Tabs } from "@mart369/ui/tabs";
import { FixRecord } from "../screen/fix_record";
import { errorText } from "../screen/fix_popup";
import { FixSort, readSort, saveSort, sortRows } from "../list_sort";

const MODEL = "online.service.order";
const POLL_MS = 20000;
const PRESENCE_EVENT = "fix_desk_presence";
// the cards' order, chosen above the list: [key, label, field, direction]
const SORTS = [
    ["oldest", _t("Oldest first"), "created", "asc"],
    ["newest", _t("Newest first"), "created", "desc"],
    ["visit_soon", _t("Visit time: soonest"), "slot_start", "asc"],
    ["visit_late", _t("Visit time: latest"), "slot_start", "desc"],
];
// Each tab starts in the order that suits it: waiting customers - the longest wait first; a visit
// time fixed - the next visit first; finished - the latest first. A choice made on a tab is kept
// (in this browser) for that tab only.
const STAGE_SORT = {
    new: "oldest", calling: "oldest", approved: "oldest",
    booked: "visit_soon", to_assign: "visit_soon", assigned: "visit_soon", live: "visit_soon", working: "visit_soon",
    done_today: "newest", rejected: "newest",
};
const SORT_KEY = "fix_desk_sort";
const SEARCH_MS = 300;      // the search waits this long after the last key
const sortFor = (stage) => readSort(`${SORT_KEY}:${stage}`, SORTS, STAGE_SORT[stage] || "oldest");

// What each stage means, under its title.
const HINTS = {
    new: "Website bookings waiting for a decision: approve, call the customer or reject.",
    calling: "Somebody is on the phone with the customer.",
    approved: "Approved; the customer has the estimate and a link to pick a time. The technician chosen at approval gets the link once they pick it.",
    booked: "The customer picked a time. Press Seen so the ding-dong stops. A technician chosen at approval already has the link.",
    to_assign: "Time booked and seen: choose the technician and send them the link.",
    assigned: "The technician has the link; waiting for them to set off.",
    live: "On the way or at the door: the map follows the technician's phone.",
    working: "Repair in progress (at the door or at the office).",
    done_today: "Visits finished today.",
    rejected: "Rejected today, with the reason sent to the customer.",
};

const BUTTONS = {
    approve: { label: "Approve", kind: "primary", icon: "fa-check" },
    book_time: { label: "Book a time", kind: "primary", icon: "fa-calendar-plus-o" },
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
    check_result: { label: "What did you find?", kind: "primary", icon: "fa-search" },
    fixed: { label: "Fixed on the spot", kind: "ghost", icon: "fa-check-circle" },
    approved_here: { label: "Customer approved", kind: "primary", icon: "fa-thumbs-up" },
    declined_here: { label: "Customer declined", kind: "danger-ghost", icon: "fa-thumbs-down" },
    later: { label: "Decides later", kind: "ghost", icon: "fa-clock-o" },
    repair_done: { label: "Repair done", kind: "primary", icon: "fa-check-circle" },
    take: { label: "Take the device", kind: "primary", icon: "fa-building" },
    office: { label: "Repair at office", kind: "ghost", icon: "fa-building" },
    cancel_visit: { label: "Cancel visit", kind: "danger-ghost", icon: "fa-ban" },
    office_received: { label: "Received at the office", kind: "primary", icon: "fa-building" },
    part_found: { label: "Part found: add it", kind: "primary", icon: "fa-check" },
    part_none: { label: "Not available", kind: "danger-ghost", icon: "fa-times" },
    finish_skip: { label: "Finish without code", kind: "ghost", icon: "fa-flag-checkered" },
};

export class FixDesk extends Component {
    static template = "369ai_fix.Desk";
    static components = { Layout, FixRecord, FixSort, Tabs };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.bus = useService("bus_service");
        this.notification = useService("notification");
        // every pop-up of the desk is a green one (static/src/app/screen/fix_popup.js)
        this.popup = useService("fix_popup");
        this.mapRef = useRef("map");
        this.state = useState({
            loading: true,
            stage: "new",
            stages: [],
            counts: {},
            rows: [],
            sort: sortFor("new"),
            since: "",
            technicians: [],
            ring: 20,
            repeat: 15,
            newOn: true,
            slotOn: true,
            slotRing: 20,
            slotRepeat: 15,
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
            askFinish: false,
            finishReason: "",
            askNone: false,     // "Not available" for a part the technician asked: the reason box
            noneReason: "",
            partAsks: 0,        // technicians waiting at a door for the office's answer about a part
            searchQ: "",        // the search box (every booking, any stage and date)
            searching: false,
            found: null,        // the search's bookings (null: not searched yet)
            foundCount: 0,      // how many match in all (the newest 50 are listed)
            media: null,      // the customer's photo / video open in the viewer
            // the pane's tabs: the overview, or the booking / a job card / the visit drawn by
            // the green record screen, or the notes of all three
            paneTab: "overview",
            paneCard: 0,
            notes: [],
            noteText: "",
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
            // opened from a booking's "Open on the Booking Desk" or the alarm: show that booking
            const ctx = (this.props.action && this.props.action.context) || {};
            if (ctx.fix_desk_order_id) {
                this.select({ id: ctx.fix_desk_order_id });
            }
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
            clearTimeout(this.searchTimer);
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

    // ------------------------------------------------------------------ the list's order
    get sorts() {
        return SORTS;
    }

    get sortedRows() {
        return sortRows(this.state.rows, SORTS, this.state.sort);
    }

    /** What the list draws: the tab's cards; while searching, the results grouped by stage in
     *  the rail's order (older done / cancelled bookings last), each group under a heading line. */
    get listItems() {
        if (!this.searchActive) {
            return this.sortedRows.map((row) => ({ key: row.id, row }));
        }
        const order = this.state.stages.map((s) => s.key);
        const groups = new Map();
        for (const row of this.state.found || []) {
            const key = row.stage !== "other" ? row.stage : `other:${row.stage_label}`;
            if (!groups.has(key)) {
                groups.set(key, { key, stage: row.stage, head: row.stage_label || _t("Other"), rows: [] });
            }
            groups.get(key).rows.push(row);
        }
        const rank = (g) => (g.stage === "other" ? order.length : Math.max(0, order.indexOf(g.stage)));
        const items = [];
        for (const g of [...groups.values()].sort((a, b) => rank(a) - rank(b))) {
            items.push({ key: `head:${g.key}`, head: g.head, stage: g.stage, count: g.rows.length });
            items.push(...g.rows.map((row) => ({ key: row.id, row })));
        }
        return items;
    }

    // ------------------------------------------------------------------ search every booking
    get searchActive() {
        return this.state.searchQ.trim().length >= 2;
    }

    onSearch(ev) {
        this.state.searchQ = ev.target.value;
        clearTimeout(this.searchTimer);
        if (!this.searchActive) {
            this.searchSeq = (this.searchSeq || 0) + 1;
            Object.assign(this.state, { found: null, foundCount: 0, searching: false });
            return;
        }
        this.state.searching = true;
        this.searchTimer = setTimeout(() => this.runSearch(), SEARCH_MS);
    }

    onSearchKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            clearTimeout(this.searchTimer);
            this.runSearch();
        } else if (ev.key === "Escape") {
            this.clearSearch();
        }
    }

    async runSearch() {
        const query = this.state.searchQ.trim();
        if (query.length < 2) {
            return;
        }
        const seq = (this.searchSeq = (this.searchSeq || 0) + 1);   // only the latest words' answer is shown
        this.state.searching = true;
        try {
            const res = await this.orm.silent.call(MODEL, "fix_desk_search", [], { query });
            if (seq === this.searchSeq) {
                this.state.found = res.rows || [];
                this.state.foundCount = res.count || 0;
            }
        } catch (err) {
            if (seq === this.searchSeq) {
                this.notification.add(errorText(err), { type: "danger" });
            }
        } finally {
            if (seq === this.searchSeq) {
                this.state.searching = false;
            }
        }
    }

    clearSearch() {
        clearTimeout(this.searchTimer);
        this.searchSeq = (this.searchSeq || 0) + 1;
        Object.assign(this.state, { searchQ: "", found: null, foundCount: 0, searching: false });
    }

    setSort(key) {
        this.state.sort = key;
        saveSort(`${SORT_KEY}:${this.state.stage}`, key);
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
        s.partAsks = data.part_asks || 0;
        s.pollReady = data.poll_ready;
        s.hasCalling = data.has_calling;
        // each alarm has its own switch, ring and pause (Booking Desk Settings)
        const sound = {
            ring: data.ring, repeat: data.repeat, newOn: data.new_on !== false,
            slotRing: data.slot_ring || data.ring, slotRepeat: data.slot_repeat || data.repeat,
            slotOn: data.slot_on !== false,
        };
        if (Object.keys(sound).some((k) => sound[k] !== s[k])) {
            Object.assign(s, sound);
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
            if (s.selectedId && s.detail && !this.searchActive && !s.rows.some((r) => r.id === s.selectedId)) {
                // the booking moved to another stage: keep its detail, say so
                s.detail.moved = true;
            }
        }
        return changed;
    }

    /** The stages as 369 Mart tabs: [key, label, count]. */
    get stageTabs() {
        return this.state.stages.map((s) => [s.key, s.label, this.state.counts[s.key] || 0]);
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
                    // the technician already on it, unless they are off that day
                    const tech = this.state.technicians.find((t) => t.id === detail.visit.technician_id);
                    this.state.techPick = tech && this.offOn(tech, detail) ? 0 : detail.visit.technician_id;
                }
            }
        } catch {
            // keeps what it had
        }
        this.state.detailLoading = false;
    }

    /** A pill at the top ("5 new", "2 times booked", "1 part asked"): its tab, out of any search;
     *  `pick(row)` opens the first booking it matches (the one waiting on a part answer). */
    async goTo(stage, pick = null) {
        await this.setStage(stage);
        const row = pick && this.sortedRows.find(pick);
        if (row) {
            this.select(row);
        }
    }

    /** A tab (the rail, or a pill): always out of the search, so the tab's list shows. */
    setStage(key) {
        this.clearSearch();
        if (key === this.state.stage) {
            return Promise.resolve();
        }
        this.state.stage = key;
        this.state.sort = sortFor(key);
        this.state.rows = [];
        this.state.since = "";
        this.state.loading = true;
        this.closeDetail();
        return this.load({ force: true });
    }

    select(row) {
        this.state.selectedId = row.id;
        this.state.showDetail = true;
        this.state.askCancel = false;
        this.state.askNone = false;
        this.state.detail = null;
        this.state.paneTab = "overview";
        this.state.paneCard = 0;
        this.loadDetail();
    }

    closeDetail() {
        this.state.selectedId = 0;
        this.state.detail = null;
        this.state.showDetail = false;
        this.state.askCancel = false;
        this.state.paneTab = "overview";
    }

    /** The bill: with tax (Easy Sales) or without (Estimate Sale). A price already sent changes. */
    async setBill(type) {
        const d = this.state.detail;
        if (!d || d.bill_type === type || d.bill_locked) {
            return;
        }
        const text = type === "easy"
            ? _t("Bill %s with tax (Easy Sales)? The customer's price then includes VAT; a price already sent goes to them again with the new total.", d.name)
            : _t("Bill %s without tax (Estimate Sale)? A price already sent goes to the customer again with the new total.", d.name);
        if (await this.popup.confirm(text)) {
            await this.act("bill_type", { bill_type: type });
        }
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
        if (what === "finish_skip" && !this.state.askFinish) {
            this.state.askFinish = true;
            this.state.finishReason = "";
            return;
        }
        if (what === "part_none" && !this.state.askNone) {
            // "Not available": the technician reads why
            this.state.askNone = true;
            this.state.noneReason = "";
            return;
        }
        if (what === "book_time") {
            // staff pick the visit time for the customer (on the phone): the green time picker
            if (await this.popup.pickSlot(id)) {
                await this.load({ force: true });
            }
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
            if (what === "finish_skip") {
                kwargs.reason = this.state.finishReason;
            }
            if (what === "part_none") {
                kwargs.reason = this.state.noneReason;
            }
            let res;
            try {
                res = await this.orm.silent.call(MODEL, "fix_desk_act", [[id], what], kwargs);
            } catch (err) {
                // said on the desk, not in an Odoo window
                this.notification.add(errorText(err), { type: "danger" });
                return;
            }
            this.state.askCancel = false;
            this.state.askFinish = false;
            this.state.askNone = false;
            if (res && res.action) {
                // a wizard: drawn as a green pop-up (only what stays in Odoo goes to Odoo)
                await this.popup.doAction(res.action, { onClose: () => this.load({ force: true }) });
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

    /** Is this technician off on the booking's day (Configuration > Days Off)? */
    offOn(tech, d) {
        return !!(d && d.slot_date && tech && (tech.off || []).includes(d.slot_date));
    }

    offNames(d) {
        return this.state.technicians.filter((t) => this.offOn(t, d)).map((t) => t.name).join(", ");
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
        const newRings = s.newOn && s.counts.new > 0;
        if (newRings) {
            this.newLoop.start(s.ring, s.repeat);
        } else {
            this.newLoop.stop();
        }
        // a booked time nobody has seen, or a technician waiting at a door for a part answer
        if (s.slotOn && (s.counts.booked > 0 || s.partAsks > 0)) {
            // half a cycle later, so the two tones never sound together
            this.slotLoop.start(s.slotRing, s.slotRepeat, newRings ? ((s.ring + s.repeat) * 1000) / 2 : 0);
        } else {
            this.slotLoop.stop();
        }
    }

    // ------------------------------------------------------------------ open things
    /** The customer's photo or video in a viewer on this page (Esc or a click outside closes it). */
    openMedia(type, id) {
        this.state.media = { type, src: `/web/content/${id}` };
        this._mediaKey = (ev) => ev.key === "Escape" && this.closeMedia();
        document.addEventListener("keydown", this._mediaKey);
    }

    closeMedia() {
        this.state.media = null;
        if (this._mediaKey) {
            document.removeEventListener("keydown", this._mediaKey);
            this._mediaKey = null;
        }
    }

    /** "Open form" and the job card / visit links: the record opens in a tab of this pane. */
    openForm(model, id) {
        if (!id) {
            return;
        }
        if (model === "job.card") {
            this.state.paneCard = id;
            this.setTab("card");
        } else if (model === "fix.service.visit") {
            this.setTab("visit");
        } else {
            this.setTab("booking");
        }
    }

    openAll() {
        this.popup.openScreen({ screen: "bookings" });
    }

    // ------------------------------------------------------------------ the pane's tabs
    get paneTabs() {
        const d = this.state.detail;
        if (!d) {
            return [];
        }
        const tabs = [{ key: "overview", label: _t("Overview"), icon: "fa-dashboard" },
                      { key: "booking", label: _t("Booking"), icon: "fa-calendar-check-o" }];
        if (d.job_cards && d.job_cards.length) {
            tabs.push({ key: "card", label: _t("Job card"), icon: "fa-file-text-o" });
        }
        if (d.visit) {
            tabs.push({ key: "visit", label: _t("Visit"), icon: "fa-car" });
        }
        tabs.push({ key: "notes", label: _t("Notes"), icon: "fa-comments-o" });
        const wa = (d.whatsapp || []).length;
        tabs.push({ key: "whatsapp", label: wa ? _t("WhatsApp (%s)", wa) : _t("WhatsApp"), icon: "fa-whatsapp" });
        return tabs;
    }

    /** A WhatsApp text as pieces, its web links tappable (drawn by the template, never as HTML). */
    waParts(text) {
        const parts = [];
        const re = /https?:\/\/[^\s<>"]+/g;
        let last = 0;
        let m;
        while ((m = re.exec(text || ""))) {
            if (m.index > last) {
                parts.push({ link: false, text: text.slice(last, m.index) });
            }
            const url = m[0].replace(/[.,;:!?)]+$/, "");
            parts.push({ link: true, text: url });
            last = m.index + url.length;
        }
        if (last < (text || "").length) {
            parts.push({ link: false, text: text.slice(last) });
        }
        return parts;
    }

    get cardId() {
        const cards = (this.state.detail && this.state.detail.job_cards) || [];
        return cards.some((c) => c.id === this.state.paneCard) ? this.state.paneCard : (cards[0] && cards[0].id) || 0;
    }

    setTab(key) {
        this.state.paneTab = key;
        if (key === "notes") {
            this.loadNotes();
        }
    }

    /** A change made in a tab: the cards and the overview follow. */
    onPaneChanged() {
        this.load({ force: true });
    }

    noteTargets() {
        const d = this.state.detail;
        const targets = [["bookings", d.id]];
        for (const card of d.job_cards || []) {
            targets.push(["job_cards", card.id]);
        }
        if (d.visit) {
            targets.push(["visits", d.visit.id]);
        }
        return targets;
    }

    async loadNotes() {
        if (!this.state.detail) {
            return;
        }
        try {
            this.state.notes = await this.orm.silent.call("fix.screen", "screen_notes", [this.noteTargets()]);
        } catch (err) {
            this.notification.add(errorText(err), { type: "danger" });
        }
    }

    async addNote() {
        const body = this.state.noteText.trim();
        if (!body || !this.state.detail) {
            return;
        }
        try {
            await this.orm.silent.call("fix.screen", "screen_note", ["bookings", this.state.detail.id, body]);
            this.state.noteText = "";
            await this.loadNotes();
        } catch (err) {
            this.notification.add(errorText(err), { type: "danger" });
        }
    }

    noteWhen(note) {
        return this.when(note.date);
    }

    noteText(note) {
        // parsed, never run: DOMParser does not load images or start scripts
        return new DOMParser().parseFromString(note.body || "", "text/html").body.textContent.trim();
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
