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
import { errorText } from "../screen/fix_popup";

const MODEL = "fix.service.visit";
const POLL_MS = 30000;
const FEW_ISSUES = 12;
const VIDEO_BYTES = 30 * 1024 * 1024;

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
const OUTCOME_ICONS = { parts: "fa-cogs", labour: "fa-wrench", lab: "fa-flask", no_fault: "fa-check",
                        not_worth: "fa-ban", warranty: "fa-certificate" };

export class FixTech extends Component {
    static template = "369ai_fix.Tech";
    static components = { Layout };
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
        return this.state.visits.filter((v) => v.state !== "done");
    }

    get doneVisits() {
        return this.state.visits.filter((v) => v.state === "done");
    }

    async open(visit) {
        this.state.selectedId = visit.id;
        this.state.showDetail = true;
        Object.assign(this.state, { message: "", code: "", found: [], query: "", plan: "", accIds: [], noAcc: false,
                                    issuesOpen: false, issueWord: "", brandId: 0, partDaysSet: false,
                                    outcome: "", prices: {}, labourPrice: "", alts: [], altsFor: 0, reqOpen: false,
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
            if (action !== "ping" && !action.startsWith("check_")) {
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
        return !!(v && v.state === "arrived" && v.checks && v.checks.missing && v.checks.missing.length);
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

    money(value) {
        const r = this.result || {};
        return `${r.currency || ""} ${Number(value || 0).toFixed(r.decimals ?? 2)}`.trim();
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

    async search(ev) {
        if (ev) {
            ev.preventDefault();
        }
        const res = await this.act("result_parts", { query: this.state.query });
        this.state.found = (res && res.parts) || [];
        if (res && res.ok !== false && !this.state.found.length) {
            this.state.message = _t("No part found. Try another word.");
        }
    }

    async addPart(part) {
        if (this.needBrand()) {
            return;
        }
        const res = await this.act("result_add_part", { product_id: part.product_id, brand_id: this.state.brandId || false });
        if (res && res.ok !== false) {
            this.state.found = [];
            this.state.query = "";
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
            if (!(await this.popup.confirm(_t("Close the visit without a repair? The customer gets your reason on WhatsApp.")))) {
                return;
            }
            await this.act("result_outcome", { outcome: key, note: this.state.note });
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

    async requestPart() {
        if (this.needBrand()) {
            return;
        }
        if (this.state.reqName.trim().length < 2) {
            this.state.message = _t("Type the part's name.");
            return;
        }
        if (!(await this.popup.confirm(_t("Ask the office for this part? The visit closes; the customer is told the price follows.")))) {
            return;
        }
        await this.act("result_request", { name: this.state.reqName.trim(), price: Number(this.state.reqPrice) || 0,
                                           data: this.state.reqPhoto || "", note: this.state.note, brand_id: this.state.brandId || false });
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
