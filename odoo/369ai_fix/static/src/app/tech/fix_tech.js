/** @odoo-module **/

/**
 * My Visits: the technician's own screen in Odoo, the same steps as their web page from
 * WhatsApp (src/pages/tech.astro on the website), with their Odoo login.
 *
 *   my visits (left)        | the visit (right)
 *   · today's and upcoming  |   customer, address, time, Call / Directions
 *   · done today            |   Start trip -> I have arrived (code) -> Before you start
 *                           |   (safety, photos, video) -> Start work -> What did you find?
 *                           |   (can it be fixed? parts, labour price, a part from the office,
 *                           |   two grades) -> quotation -> customer's answer -> repair done /
 *                           |   take device -> Finish (after photo, payment, finish code)
 *
 * Every step goes through fix.service.visit.fix_tech_act (app/models/fix_tech.py), which checks
 * the visit is the user's own and runs the web page's own step (_fs_tech_do). While a visit is
 * open the screen shares the phone's location, like the web page.
 */

import { Component, onWillStart, onWillUnmount, useEffect, useExternalListener, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Layout } from "@web/search/layout";
import { Tabs } from "@mart369/ui/tabs";
import { errorText } from "../screen/fix_popup";
import { FixSort, readSort, saveSort, sortRows } from "../list_sort";

const MODEL = "fix.service.visit";
// the visits' order, chosen above the list: [key, label, field, direction]
const SORTS = [
    ["visit_soon", _t("Visit time: soonest"), (v) => v.slot && v.slot.start, "asc"],
    ["visit_late", _t("Visit time: latest"), (v) => v.slot && v.slot.start, "desc"],
    ["newest", _t("Newest booking first"), "created", "desc"],
    ["oldest", _t("Oldest booking first"), "created", "asc"],
];
const SORT_KEY = "fix_tech_sort";
const POLL_MS = 30000;
const ASK_POLL_MS = 10000;  // how often the office's answer about a part is looked for
const FEW_ISSUES = 12;
const VIDEO_BYTES = 30 * 1024 * 1024;
const SEARCH_MS = 300;      // the parts search waits this long after the last key

// the one button of a step: [label, action, hint]
const STEP = {
    assigned: [_t("Start trip"), "on_the_way", _t("Tap when you leave. The customer is told you are on the way.")],
    on_the_way: [_t("I have arrived"), "arrive", _t("Tap at the door.")],
    arrived: [_t("Start work"), "start", _t("Tap when you start checking the device.")],
};
const WHERE = {
    in_stock: (p) => _t("In the office (%s)", p.office),
    other_branch: (p) => _t("At %s", (p.branches || []).map((b) => `${b.name} (${b.qty})`).join(", ")),
    order: () => _t("Must be ordered"),
};
const PLANS_HERE = [["now", _t("Fix now (I have the part)")], ["take", _t("Take the device to the office")],
                    ["come_back", _t("Customer keeps it, we come back")]];
const PLANS_ORDER = [["keep", _t("Customer keeps it until the part arrives")],
                     ["order_take", _t("Take the device to the office until the part arrives")]];
// "Can it be fixed?": these close the visit with the reason the technician writes
const NO_REPAIR = ["no_fault", "not_worth", "warranty"];
const FEE_OUTCOMES = ["no_fault", "not_worth"];     // the visit fee when Repair Settings' switch is on
const OUTCOME_ICONS = { parts: "fa-cogs", labour: "fa-wrench", lab: "fa-flask", no_fault: "fa-check",
                        not_worth: "fa-ban", warranty: "fa-certificate" };

export class FixTech extends Component {
    static template = "369ai_fix.Tech";
    static components = { Layout, FixSort, Tabs };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.popup = useService("fix_popup");
        this.state = useState({
            loading: true,
            visits: [],
            linked: true,
            manager: false,
            me: "",
            selectedId: 0,
            sort: readSort(SORT_KEY, SORTS),
            findQ: "",          // the search box: my visits of any date
            finding: false,
            findRows: null,     // its visits (null: not searched yet)
            findCount: 0,       // how many match in all (the newest 50 are listed)
            view: null,
            showDetail: false,
            busy: false,
            message: "",
            code: "",
            gps: "",            // "", "on", "blocked", "none"
            // What did you find?
            note: "",
            brandId: 0,
            issuesOpen: false,
            issueWord: "",
            query: "",
            found: [],
            searching: false,   // a search for what is typed is on its way
            searched: "",       // the words the parts below were found for
            plan: "",
            days: 3,
            unit: "days",
            partDays: 7,
            partDaysSet: false,
            accIds: [],
            noAcc: false,
            // can it be fixed? (lab / no repair are chosen here, then confirmed)
            outcome: "",
            labDays: 3,
            labUnit: "days",
            prices: {},         // typed labour prices, by repair line
            labourPrice: "",
            labourOpen: false,  // Labour only: the charge box open (before a charge is saved)
            waiveFee: false,    // Not worth repairing: the technician waives the visit fee at the door
            listTab: "open",    // the list shown: open | working | done | cancelled (369 Mart tiles and tabs)
            alts: [],           // other grades offered for one part
            altsFor: 0,
            reqOpen: false,
            reqName: "",
            reqPrice: "",
            reqPhoto: "",
            // finish
            payMethod: 0,
            payAmount: "",
            finishCode: "",
            today: null,
            // a photo opened big: its place in the list, its picture once loaded
            photo: { ix: -1, uri: "", name: "" },
        });
        this.fix = null;
        this.savedOutcome = "";
        this.alertRef = useRef("alert");
        // a warning shows at the top: bring it into view, the technician is often scrolled down at the button
        useEffect(
            (message) => {
                if (message && this.alertRef.el) {
                    this.alertRef.el.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            },
            () => [this.state.message]
        );
        this.watchId = null;
        this.pingTimer = null;
        this.pollTimer = null;

        onWillStart(async () => {
            await this.load();
            const first = this.state.visits.find((v) => v.state !== "done");
            if (first && window.innerWidth > 820) {
                await this.open(first);
            }
        });
        this.pollTimer = setInterval(() => {
            if (!document.hidden && !this.state.busy) {
                this.load();
            }
        }, POLL_MS);
        // waiting for the office's answer about a part: it shows here by itself
        this.askTimer = setInterval(() => this.refreshAsk(), ASK_POLL_MS);
        // the photo popup's keys: before Odoo's own shortcuts (capture), which take Escape otherwise
        useExternalListener(window, "keydown", (ev) => {
            if (this.state.photo.ix < 0 || !["Escape", "ArrowRight", "ArrowLeft"].includes(ev.key)) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            if (ev.key === "Escape") {
                this.closePhoto();
            } else {
                this.stepPhoto(ev.key === "ArrowRight" ? 1 : -1);
            }
        }, { capture: true });
        onWillUnmount(() => {
            clearInterval(this.pollTimer);
            clearTimeout(this.searchTimer);
            clearTimeout(this.findTimer);
            clearInterval(this.askTimer);
            this.stopGps();
        });
    }

    // ------------------------------------------------------------------ the list
    async load() {
        try {
            const data = await this.orm.call(MODEL, "fix_tech_load", []);
            Object.assign(this.state, {
                visits: data.visits, linked: data.linked, manager: data.manager, me: data.me, today: data.today || null,
            });
        } catch (err) {
            this.notification.add(errorText(err), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    get openVisits() {
        return sortRows(this.state.visits.filter((v) => !["done", "cancelled"].includes(v.state)), SORTS, this.state.sort);
    }

    get sorts() {
        return SORTS;
    }

    // ------------------------------------------------------------------ search my visits (any date)
    get findActive() {
        return this.state.findQ.trim().length >= 2;
    }

    onFind(ev) {
        this.state.findQ = ev.target.value;
        clearTimeout(this.findTimer);
        if (!this.findActive) {
            this.findSeq = (this.findSeq || 0) + 1;
            Object.assign(this.state, { findRows: null, findCount: 0, finding: false });
            return;
        }
        this.state.finding = true;
        this.findTimer = setTimeout(() => this.runFind(), SEARCH_MS);
    }

    onFindKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            clearTimeout(this.findTimer);
            this.runFind();
        } else if (ev.key === "Escape") {
            this.clearFind();
        }
    }

    async runFind() {
        const query = this.state.findQ.trim();
        if (query.length < 2) {
            return;
        }
        const seq = (this.findSeq = (this.findSeq || 0) + 1);       // only the latest words' answer is shown
        this.state.finding = true;
        try {
            const res = await this.orm.silent.call(MODEL, "fix_tech_search", [], { query });
            if (seq === this.findSeq) {
                this.state.findRows = res.rows || [];
                this.state.findCount = res.count || 0;
            }
        } catch (err) {
            if (seq === this.findSeq) {
                this.notification.add(errorText(err), { type: "danger" });
            }
        } finally {
            if (seq === this.findSeq) {
                this.state.finding = false;
            }
        }
    }

    clearFind() {
        clearTimeout(this.findTimer);
        this.findSeq = (this.findSeq || 0) + 1;
        Object.assign(this.state, { findQ: "", findRows: null, findCount: 0, finding: false });
    }

    setSort(key) {
        this.state.sort = key;
        saveSort(SORT_KEY, key);
    }

    get doneVisits() {
        return this.state.visits.filter((v) => v.state === "done");
    }

    get cancelledVisits() {
        return this.state.visits.filter((v) => v.state === "cancelled");
    }

    // ------------------------------------------------------------------ tiles and tabs (369 Mart)
    get workingVisits() {
        return this.openVisits.filter((v) => v.state === "in_progress");
    }

    /** The lists as tiles / tabs: [key, label, count, hint]. */
    get listTabs() {
        return [
            ["open", _t("To do"), this.openVisits.length, _t("Today and upcoming")],
            ["working", _t("Working now"), this.workingVisits.length, _t("At a customer")],
            ["done", _t("Done today"), this.doneVisits.length, this.todayText() || _t("Finished today")],
            ["cancelled", _t("Cancelled"), this.cancelledVisits.length, _t("Last 7 days")],
        ];
    }

    get tabItems() {
        return this.listTabs.map(([key, label, count]) => [key, label, count]);
    }

    get listVisits() {
        return { open: this.openVisits, working: this.workingVisits, done: this.doneVisits,
                 cancelled: this.cancelledVisits }[this.state.listTab] || this.openVisits;
    }

    pickList(key) {
        this.clearFind();
        this.state.listTab = key;
    }

    async open(visit) {
        this.state.selectedId = visit.id;
        this.state.showDetail = true;
        this.clearSearch();
        Object.assign(this.state, { message: "", code: "", plan: "", accIds: [], noAcc: false,
                                    issuesOpen: false, issueWord: "", brandId: 0, partDaysSet: false,
                                    outcome: "", prices: {}, labourPrice: "", labourOpen: false, waiveFee: false, alts: [], altsFor: 0, reqOpen: false,
                                    reqName: "", reqPrice: "", reqPhoto: "", payMethod: 0, payAmount: "", finishCode: "" });
        try {
            this.show(await this.orm.call(MODEL, "fix_tech_view", [[visit.id]]));
        } catch (err) {
            this.state.view = null;
            this.notification.add(errorText(err), { type: "danger" });
        }
    }

    // ------------------------------------------------------------------ a photo, big
    async openPhoto(ix) {
        const photos = (this.state.view && this.state.view.photos) || [];
        const p = photos[ix];
        if (!p) {
            return;
        }
        // the thumbnail at once, the full picture as soon as it comes
        this.state.photo = { ix, uri: p.uri, name: p.name };
        try {
            const big = await this.orm.call(MODEL, "fix_tech_photo", [[this.state.selectedId]], { photo_id: p.id });
            if (big.ok && this.state.photo.ix === ix) {
                this.state.photo = { ix, uri: big.uri, name: big.name || p.name };
            }
        } catch {
            // the thumbnail stays
        }
    }

    stepPhoto(delta) {
        const n = ((this.state.view && this.state.view.photos) || []).length;
        if (n > 1) {
            this.openPhoto((this.state.photo.ix + delta + n) % n);
        }
    }

    closePhoto() {
        this.state.photo = { ix: -1, uri: "", name: "" };
    }

    closeDetail() {
        this.state.showDetail = false;
    }

    show(view) {
        this.state.view = view;
        const r = view && view.result;
        if (r) {
            if (document.activeElement === null || !document.activeElement.classList.contains("fxt-note")) {
                this.state.note = r.found || "";
            }
            if (r.to_order && !this.state.partDaysSet) {
                this.state.partDays = r.part_days || 7;
            }
            const plans = this.plans;
            if (!plans.some(([key]) => key === this.state.plan)) {
                this.state.plan = plans.length ? plans[0][0] : "";
            }
            // the outcome saved on the visit wins when it changes; a choice not confirmed yet stays
            if (r.outcome && (r.outcome !== this.savedOutcome || !this.state.outcome)) {
                this.state.outcome = r.outcome;
            }
            this.savedOutcome = r.outcome || "";
        }
        const c = view && view.close;
        if (c && !this.state.payMethod && c.methods && c.methods.length) {
            this.state.payMethod = (c.methods.find((m) => m.default) || c.methods[0]).id;
        }
        if (view && view.share) {
            this.startGps(view.ping_every || 20);
        } else {
            this.stopGps();
        }
    }

    // ------------------------------------------------------------------ steps
    async act(action, args = {}, { quiet = false } = {}) {
        const id = this.state.selectedId;
        if (!id || this.state.busy) {
            return null;
        }
        this.state.busy = true;
        this.state.message = "";
        try {
            const res = await this.orm.call(MODEL, "fix_tech_act", [[id], action], { ...this.where(), ...args });
            if (res && res.ref) {
                this.show(res);
            }
            if (res && res.ok === false && !quiet) {
                this.state.message = res.message || _t("That did not work. Try again.");
            }
            if (action !== "ping" && !action.startsWith("check_") && !action.startsWith("tool_")) {
                this.load();
            }
            return res;
        } catch (err) {
            if (!quiet) {
                this.state.message = errorText(err);
            }
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    get step() {
        const v = this.state.view;
        return v ? STEP[v.state] : null;
    }

    get stepBlocked() {
        const v = this.state.view;
        return !!(v && v.state === "arrived" && v.checks && v.checks.missing && v.checks.missing.length) || this.toolsBlock;
    }

    get stepBlockedText() {
        const v = this.state.view;
        if (this.toolsBlock) {
            return _t("Check your tools first (above).");
        }
        return _t("Still to do: %s.", ((v.checks && v.checks.missing) || []).join(", "));
    }

    // ------------------------------------------------------------------ the tool bag
    get toolsBlock() {
        const v = this.state.view;
        return !!(v && v.state === "assigned" && v.tools && v.tools.required && !v.tools.done);
    }

    // "Before you leave" is open and not done: the steps that end the visit wait for it
    get toolsLock() {
        const v = this.state.view;
        return !!(v && v.state === "in_progress" && v.tools && v.tools.kind === "house" && v.tools.required && !v.tools.done);
    }

    get toolsTitle() {
        const t = this.state.view.tools;
        return t.for_ref ? _t("Tools: the house you left (%s)", t.for_customer || t.for_ref) : t.title;
    }

    get toolsHint() {
        const t = this.state.view.tools;
        if (t.for_ref) {
            return _t("You left %(customer)s (%(ref)s) without checking your tools. Do it now, before the next trip.",
                      { customer: t.for_customer || _t("the customer"), ref: t.for_ref });
        }
        return t.kind === "office"
            ? _t("Before you leave the office: mark each tool and take a photo of the open bag. A missing tool does not stop you; the office is told.")
            : _t("Before you leave the customer: every tool back in the bag, then a photo of the open bag.");
    }

    async toolsDone() {
        const gone = this.state.view.tools.lines.filter((line) => line.state === "missing").map((line) => line.name);
        if (gone.length && !(await this.popup.confirm(_t("Missing: %s. The office is told. Carry on?", gone.join(", "))))) {
            return;
        }
        await this.act("tool_done");
    }

    async onStep() {
        const step = this.step;
        if (!step) {
            return;
        }
        if (step[1] === "arrive" && this.state.view.need_code && !/^\d{4}$/.test(this.state.code.trim())) {
            this.state.message = _t("Type the customer's 4-digit code.");
            return;
        }
        await this.act(step[1], step[1] === "arrive" ? { code: this.state.code.trim() } : {});
        this.state.code = "";
    }

    // ------------------------------------------------------------------ location
    where() {
        const f = this.fix;
        return f ? { lat: f.coords.latitude, lng: f.coords.longitude, accuracy: f.coords.accuracy,
                     heading: f.coords.heading, speed: f.coords.speed } : {};
    }

    startGps(every) {
        if (this.watchId !== null || !navigator.geolocation) {
            if (!navigator.geolocation) {
                this.state.gps = "none";
            }
            return;
        }
        this.watchId = navigator.geolocation.watchPosition(
            (pos) => { this.fix = pos; this.state.gps = "on"; },
            (err) => { this.state.gps = err && err.code === 1 ? "blocked" : "none"; },
            { enableHighAccuracy: true, maximumAge: 10000, timeout: 30000 },
        );
        this.pingTimer = setInterval(() => {
            if (this.fix && !this.state.busy) {
                this.orm.silent.call(MODEL, "fix_tech_act", [[this.state.selectedId], "ping"], this.where()).catch(() => {});
            }
        }, Math.max(every, 10) * 1000);
    }

    stopGps() {
        if (this.watchId !== null && navigator.geolocation) {
            navigator.geolocation.clearWatch(this.watchId);
        }
        clearInterval(this.pingTimer);
        this.watchId = null;
        this.pingTimer = null;
        this.state.gps = "";
    }

    // ------------------------------------------------------------------ before you start
    async warranty(answer) {
        if (answer.key === "keep" && !(await this.popup.confirm(
            _t("The customer keeps the brand's warranty? The visit closes now, nothing is opened, and the customer gets a polite message.")))) {
            return;
        }
        await this.act("check_warranty", { answer: answer.key });
    }

    async tick(item, ev) {
        await this.act("check_tick", { item_id: item.id, done: ev.target.checked });
    }

    async photo(action, ev, extra = {}) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        await this.act(action, { ...extra, data: await shrink(file) });
    }

    async video(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (file.size > VIDEO_BYTES) {
            this.state.message = _t("The video is too large. Record a shorter one (under a minute).");
            return;
        }
        await this.act("check_video", { name: file.name, data: await asBase64(file) });
    }

    // ------------------------------------------------------------------ what did you find?
    get result() {
        return (this.state.view && this.state.view.result) || null;
    }

    get issues() {
        const all = (this.result && this.result.issues) || [];
        if (this.state.issuesOpen) {
            const word = this.state.issueWord.trim().toLowerCase();
            return all.filter((i) => i.on || !word || i.name.toLowerCase().includes(word));
        }
        return all.filter((i, n) => i.on || n < FEW_ISSUES);
    }

    get hiddenIssues() {
        const all = (this.result && this.result.issues) || [];
        return this.state.issuesOpen ? 0 : all.length - this.issues.length;
    }

    toggleIssues() {
        this.state.issuesOpen = !this.state.issuesOpen;
        this.state.issueWord = "";
    }

    get ticked() {
        return ((this.result && this.result.issues) || []).some((i) => i.on);
    }

    get plans() {
        const r = this.result;
        return r && r.to_order ? PLANS_ORDER : PLANS_HERE;
    }

    money(value, currency = "") {
        const r = this.result || {};
        return `${currency || r.currency || ""} ${Number(value || 0).toFixed(r.decimals ?? 3)}`.trim();
    }

    whereText(part) {
        return (WHERE[part.status] || (() => ""))(part);
    }

    needBrand() {
        if (this.result && this.result.need_device && !this.state.brandId) {
            this.state.message = _t("Choose the device brand first.");
            return true;
        }
        return false;
    }

    async toggleIssue(issue) {
        if (this.needBrand()) {
            return;
        }
        await this.act("result_issue", { issue_id: issue.id, on: !issue.on, brand_id: this.state.brandId || false });
    }

    async saveNote() {
        // in the background: leaving the note box for a button must not grey that button out
        // (the steps that close the visit send the note themselves)
        const id = this.state.selectedId;
        const note = this.state.note;
        if (!id || !this.result || (this.result.found || "") === note) {
            return;
        }
        try {
            const res = await this.orm.call(MODEL, "fix_tech_act", [[id], "result_note"], { ...this.where(), note });
            if (res && res.result && this.state.selectedId === id && this.result) {
                this.result.found = res.result.found;
            }
        } catch {
            // the next step sends the note again
        }
    }

    // ------------------------------------------------------------------ the parts search, as you type
    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.searchTimer);
        if (this.state.query.trim().length < 2) {
            this.clearSearch(false);
            return;
        }
        this.state.searching = true;
        this.searchTimer = setTimeout(() => this.search(), SEARCH_MS);
    }

    onQueryKey(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            clearTimeout(this.searchTimer);
            this.search();
        }
    }

    async search() {
        const id = this.state.selectedId;
        const query = this.state.query.trim();
        if (!id || query.length < 2) {
            return;
        }
        const seq = ++this.searchSeq;      // only the answer for the latest words is shown
        this.state.searching = true;
        try {
            const res = await this.orm.silent.call(MODEL, "fix_tech_act", [[id], "result_parts"], { query });
            if (seq !== this.searchSeq) {
                return;
            }
            this.state.found = (res && res.parts) || [];
            this.state.searched = query;
        } catch {
            if (seq === this.searchSeq) {
                this.state.found = [];
                this.state.searched = "";
            }
        } finally {
            if (seq === this.searchSeq) {
                this.state.searching = false;
            }
        }
    }

    clearSearch(words = true) {
        clearTimeout(this.searchTimer);
        this.searchSeq = (this.searchSeq || 0) + 1;
        Object.assign(this.state, { found: [], searching: false, searched: "" });
        if (words) {
            this.state.query = "";
        }
    }

    askOfficeFor(words) {
        // not in the list: open "Ask the office" with the part's name filled in
        Object.assign(this.state, { reqOpen: true, reqName: this.state.reqName || words });
    }

    async addPart(part) {
        if (this.needBrand()) {
            return;
        }
        const res = await this.act("result_add_part", { product_id: part.product_id, brand_id: this.state.brandId || false });
        if (res && res.ok !== false) {
            this.clearSearch();
        }
    }

    async removePart(line) {
        await this.act("result_remove_part", { line_id: line.line_id });
    }

    async fixedHere() {
        const r = this.result;
        const text = r && !Number(r.total)
            ? _t("Fixed on the spot, with no charge? Next: a photo of the repaired device and the customer's finish code.")
            : _t("Fixed on the spot? Next: a photo of the repaired device, the payment and the customer's finish code.");
        if (await this.popup.confirm(text)) {
            await this.act("result_fixed", { note: this.state.note });
        }
    }

    async sendQuote() {
        const plan = this.state.plan;
        const r = this.result;
        if (!plan) {
            this.state.message = _t("Choose what happens after the customer approves.");
            return;
        }
        const days = Number(this.state.days);
        if (["take", "come_back", "order_take"].includes(plan)
                && !(this.state.unit === "weeks" ? days >= 1 && days <= 8 : days >= 1 && days <= 60)) {
            this.state.message = _t("How long to fix? 1 to 60 days, or 1 to 8 weeks.");
            return;
        }
        const partDays = Number(this.state.partDays);
        if (r.to_order && !(partDays >= 1 && partDays <= 120)) {
            this.state.message = _t("When does the part arrive? Give the days (1 to 120).");
            return;
        }
        if (await this.popup.confirm(_t("Send the quotation to the customer?"))) {
            await this.act("result_quote", { plan, days, unit: this.state.unit, part_days: partDays, note: this.state.note });
        }
    }

    async answer(action, text) {
        if (await this.popup.confirm(text)) {
            await this.act(action);
        }
    }

    toggleAcc(id) {
        const ids = this.state.accIds;
        this.state.accIds = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
    }

    async takeDevice() {
        if (!this.state.noAcc && !this.state.accIds.length) {
            this.state.message = _t("Tick what you take with the device, or \"Device only\".");
            return;
        }
        await this.act("result_take", { no_accessories: this.state.noAcc, accessory_ids: this.state.noAcc ? [] : this.state.accIds });
    }

    // ------------------------------------------------------------------ can it be fixed?
    get outcomeNeedsParts() {
        return this.state.outcome === "parts";
    }

    get outcomePriced() {
        return ["parts", "labour"].includes(this.state.outcome);
    }

    get outcomeCloses() {
        return NO_REPAIR.includes(this.state.outcome);
    }

    // No fault found / not worth repairing: the visit fee is charged when Repair Settings' switch is on
    // (never on a free re-check); for Not worth repairing the technician may waive it
    get feeDue() {
        const r = this.result;
        return FEE_OUTCOMES.includes(this.state.outcome) && !!r && !!r.visit_fee && !r.recheck;
    }

    get feeWaivable() {
        return this.feeDue && this.state.outcome === "not_worth";
    }

    get chargingVisitFee() {
        return this.feeDue && !(this.feeWaivable && this.state.waiveFee);
    }

    outcomeIcon(key) {
        return OUTCOME_ICONS[key] || "fa-circle";
    }

    async chooseOutcome(key) {
        if (this.needBrand()) {
            return;
        }
        this.state.outcome = key;
        if (["parts", "labour"].includes(key)) {
            await this.act("result_outcome", { outcome: key, note: this.state.note, brand_id: this.state.brandId || false });
        }
    }

    async confirmOutcome() {
        const key = this.state.outcome;
        if (this.outcomeCloses) {
            if (!this.state.note.trim()) {
                this.state.message = _t("Write what you checked and why it is not repaired: the customer reads it.");
                return;
            }
            const fee = this.chargingVisitFee;
            if (!(await this.popup.confirm(fee
                ? _t("Charge the visit fee? The customer gets your reason and a finish code; they pay you, then give you the code.")
                : _t("Close the visit without a repair? The customer gets your reason on WhatsApp.")))) {
                return;
            }
            await this.act("result_outcome", { outcome: key, note: this.state.note, fee,
                                               waive: this.feeWaivable && this.state.waiveFee,
                                               brand_id: this.state.brandId || false });
        } else if (key === "lab") {
            const days = Number(this.state.labDays);
            if (!(this.state.labUnit === "weeks" ? days >= 1 && days <= 8 : days >= 1 && days <= 60)) {
                this.state.message = _t("When will the price be ready? 1 to 60 days, or 1 to 8 weeks.");
                return;
            }
            if (await this.popup.confirm(_t("Take the device to the lab? The customer is told the price follows."))) {
                await this.act("result_outcome", { outcome: key, note: this.state.note, days, unit: this.state.labUnit,
                                                   brand_id: this.state.brandId || false });
            }
        }
    }

    // ------------------------------------------------------------------ Spin & Win: the prize handed over
    async prizeGiven() {
        if (await this.popup.confirm(_t("The customer got the prize?"))) {
            await this.act("prize_given");
        }
    }

    // ------------------------------------------------------------------ the labour price
    priceOf(svc) {
        const key = svc.line_id || `p${svc.product_id}`;
        return key in this.state.prices ? this.state.prices[key] : svc.price;
    }

    setPrice(svc, value) {
        this.state.prices[svc.line_id || `p${svc.product_id}`] = value;
    }

    async savePrice(svc) {
        if (this.needBrand()) {
            return;
        }
        const value = this.priceOf(svc);
        if (value === "" || Number(value) === Number(svc.price)) {
            return;
        }
        const price = Number(value);
        if (!(price >= 0)) {
            this.state.message = _t("Type a price of 0 or more.");
            return;
        }
        await this.act("result_price", { price, line_id: svc.line_id || false,
                                         product_id: svc.line_id ? false : svc.product_id, brand_id: this.state.brandId || false });
        this.state.prices = {};
    }

    async addLabour() {
        if (this.needBrand()) {
            return;
        }
        const price = Number(this.state.labourPrice);
        if (this.state.labourPrice === "" || !(price >= 0)) {
            this.state.message = _t("Type the labour price.");
            return;
        }
        const res = await this.act("result_price", { price, brand_id: this.state.brandId || false });
        if (res && res.ok !== false) {
            this.state.labourPrice = "";
        }
    }

    // ------------------------------------------------------------------ Labour only: free, or a charge
    get labourFree() {
        const r = this.result;
        return !!r && r.labour === "free" && !this.state.labourOpen;
    }

    async setLabourFree(free) {
        if (free) {
            this.state.labourOpen = false;
            this.state.labourPrice = "";
            await this.act("result_labour", { price: 0, brand_id: this.state.brandId || false });
        } else {
            this.state.labourOpen = true;      // the charge box shows; nothing is charged until Save
        }
    }

    async saveLabour() {
        if (this.needBrand()) {
            return;
        }
        const price = Number(this.state.labourPrice);
        if (this.state.labourPrice === "" || !(price >= 0)) {
            this.state.message = _t("Type the labour charge.");
            return;
        }
        const res = await this.act("result_labour", { price, brand_id: this.state.brandId || false });
        if (res && res.ok !== false) {
            Object.assign(this.state, { labourPrice: "", labourOpen: false });
        }
    }

    // a fixed labour price from the office's list: the server sets its name and price
    async useLabourPreset(preset) {
        if (this.needBrand()) {
            return;
        }
        const res = await this.act("result_labour", { preset_id: preset.id, brand_id: this.state.brandId || false });
        if (res && res.ok !== false) {
            Object.assign(this.state, { labourPrice: "", labourOpen: false });
        }
    }

    labourPresetOn(preset) {
        const r = this.result;
        return !!r && r.labour !== "free" && Number(r.labour) === Number(preset.price);
    }

    // ------------------------------------------------------------------ two grades of a part
    async showAlts(line) {
        if (this.state.altsFor === line.line_id) {
            this.state.altsFor = 0;
            this.state.alts = [];
            return;
        }
        const res = await this.act("result_alts", { line_id: line.line_id });
        this.state.altsFor = line.line_id;
        this.state.alts = (res && res.alts) || [];
        if (res && res.ok !== false && !this.state.alts.length) {
            this.state.message = _t("No other grade of this part fits this device.");
        }
    }

    async addAlt(part) {
        const res = await this.act("result_add_part", { product_id: part.product_id, line_id: this.state.altsFor });
        if (res && res.ok !== false) {
            this.state.altsFor = 0;
            this.state.alts = [];
        }
    }

    async keepGrade(line) {
        if (await this.popup.confirm(_t("The customer keeps %s? The other grade is removed.", line.name))) {
            await this.act("result_choose", { line_id: line.line_id });
        }
    }

    altPartner(line) {
        return line.alt_key ? (this.result.lines || []).find((l) => l.alt_key === line.alt_key && l.line_id !== line.line_id) : null;
    }

    // ------------------------------------------------------------------ a part not in the list
    async pickReqPhoto(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (file) {
            this.state.reqPhoto = await shrink(file);
        }
    }

    /** Ask the office and wait at the door: the desk rings, the answer shows here by itself. */
    async askOffice() {
        if (this.needBrand()) {
            return;
        }
        if (this.state.reqName.trim().length < 2) {
            this.state.message = _t("Type the part's name.");
            return;
        }
        const res = await this.act("result_ask", { name: this.state.reqName.trim(), price: Number(this.state.reqPrice) || 0,
                                                   data: this.state.reqPhoto || "", note: this.state.note,
                                                   brand_id: this.state.brandId || false });
        if (res && res.ok !== false) {
            Object.assign(this.state, { reqOpen: false, reqName: "", reqPrice: "", reqPhoto: "" });
            this.clearSearch();
        }
    }

    async cancelAsk() {
        await this.act("result_ask_cancel");
    }

    /** "Don't wait": the office finds and prices the part later; the visit closes. */
    async requestPart() {
        if (this.needBrand()) {
            return;
        }
        const asked = this.result && this.result.ask && this.result.ask.state === "asked";
        if (!asked && this.state.reqName.trim().length < 2) {
            this.state.message = _t("Type the part's name.");
            return;
        }
        if (!(await this.popup.confirm(_t("Don't wait for the office? The visit closes; the office finds the part and the customer is told the price follows.")))) {
            return;
        }
        // the question already sent carries its name, price and photo
        await this.act("result_request", asked ? { note: this.state.note } : {
            name: this.state.reqName.trim(), price: Number(this.state.reqPrice) || 0,
            data: this.state.reqPhoto || "", note: this.state.note, brand_id: this.state.brandId || false });
    }

    get officeTel() {
        const phone = (this.result && this.result.office_phone) || "";
        return phone ? `tel:${phone.replace(/[^\d+]/g, "")}` : "";
    }

    /** While the technician waits for the office: the open visit is read again every few seconds. */
    async refreshAsk() {
        const r = this.result;
        const id = this.state.selectedId;
        if (!r || !r.ask || r.ask.state !== "asked" || this.state.busy || document.hidden || !id) {
            return;
        }
        try {
            const view = await this.orm.silent.call(MODEL, "fix_tech_view", [[id]]);
            if (this.state.selectedId === id && !this.state.busy && view && view.ref) {
                this.show(view);
                const ask = view.result && view.result.ask;
                if (ask && ask.state === "found") {
                    this.notification.add(_t("The office added %s to the job card.", ask.part), { type: "success" });
                } else if (ask && ask.state === "none") {
                    this.notification.add(_t("The office: %s is not available.", ask.name), { type: "warning" });
                }
            }
        } catch {
            // the next tick tries again
        }
    }

    // ------------------------------------------------------------------ finish
    get close() {
        return (this.state.view && this.state.view.close) || null;
    }

    closeMoney(value) {
        const c = this.close || {};
        return `${c.currency || ""} ${Number(value || 0).toFixed(c.decimals ?? 2)}`.trim();
    }

    async pay() {
        const c = this.close;
        if (!this.state.payMethod) {
            this.state.message = _t("Choose how the customer paid.");
            return;
        }
        const amount = this.state.payAmount === "" ? c.due : Number(this.state.payAmount);
        if (!(amount > 0) || amount > c.due + 1e-6) {
            this.state.message = _t("The amount must be more than 0 and at most %s.", this.closeMoney(c.due));
            return;
        }
        const method = (c.methods.find((m) => m.id === Number(this.state.payMethod)) || {}).name || "";
        if (await this.popup.confirm(_t("%(amount)s paid by %(method)s?", { amount: this.closeMoney(amount), method }))) {
            await this.act("close_pay", { method_id: Number(this.state.payMethod), amount });
        }
    }

    async noCharge() {
        if (await this.popup.confirm(_t("No charge for this repair?"))) {
            await this.act("close_free");
        }
    }

    async finish() {
        const code = this.state.finishCode.trim();
        if (!/^\d{4}$/.test(code)) {
            this.state.message = _t("Type the customer's 4-digit finish code.");
            return;
        }
        const res = await this.act("close_code", { code });
        if (res && res.ok !== false) {
            this.state.finishCode = "";
        }
    }

    stars(n) {
        return "★".repeat(Math.max(0, Math.min(5, Number(n) || 0)));
    }

    todayText() {
        const t = this.state.today;
        if (!t || !t.done) {
            return "";
        }
        const money = `${t.currency} ${Number(t.collected || 0).toFixed(t.decimals ?? 2)}`;
        return t.collected ? _t("Done today: %(n)s · collected %(money)s", { n: t.done, money }) : _t("Done today: %s", t.done);
    }

    stepTime(step) {
        return step.at ? new Date(step.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    }

    // ------------------------------------------------------------------ words
    /** "14:05", or "Tue 27 Oct 14:05" on another day (a server time, UTC). */
    when(value) {
        if (!value) {
            return "";
        }
        const d = new Date(value.replace(" ", "T") + "Z");
        const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        return d.toDateString() === new Date().toDateString()
            ? time : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) + " " + time;
    }

    slotText(slot) {
        if (!slot || !slot.start) {
            return "";
        }
        const start = new Date(slot.start);
        const day = start.toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
        return slot.end ? `${day} – ${new Date(slot.end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : day;
    }

    address(c) {
        return [c.building, c.floor_flat, c.address, c.area, c.landmark && _t("near %s", c.landmark)].filter(Boolean).join(", ");
    }

    telHref(phone) {
        return `tel:+${String(phone || "").replace(/\D/g, "")}`;
    }

    cardClass(v) {
        return `fxd-card fxt-card fxt-state-${v.state}${v.id === this.state.selectedId ? " fxd-on" : ""}`;
    }
}

// A phone photo is shrunk to 1600 px JPEG before it is sent (as on the web page).
async function shrink(file) {
    try {
        const img = await createImageBitmap(file);
        const k = Math.min(1, 1600 / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * k);
        canvas.height = Math.round(img.height * k);
        canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.82).split(",")[1];
    } catch {
        return asBase64(file);
    }
}

function asBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

registry.category("actions").add("369ai_fix_tech", FixTech);
