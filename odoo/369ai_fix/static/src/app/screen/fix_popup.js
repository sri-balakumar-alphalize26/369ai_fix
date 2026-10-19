/** @odoo-module **/

/**
 * Green pop-ups instead of Odoo's dialogs, for every button of the 369 ai Fix screens.
 *
 *   const popup = useService("fix_popup");
 *   popup.doAction(action, { onClose })   // an Odoo window action: a wizard opens as a green
 *                                          // pop-up, a record opens on its green screen, only
 *                                          // what stays in Odoo (invoices…) goes to Odoo
 *   popup.handle(outcome, { onClose })     // what fix.screen answered a button
 *   popup.confirm(text)                    // a green "Are you sure?" -> true / false
 *   popup.openScreen({ screen, id, filter, defaults, new })
 *   popup.create(screen, meta, defaults)   // the small "new record" pop-up -> record view
 *
 * The server side is fix.screen (app/models/fix_screen.py): screen_popup_open turns an action
 * into a pop-up, screen_popup_submit fills the wizard and presses its button, and the two
 * visit steps go through screen_checks / screen_result.
 */

import { Component, onMounted, onWillStart, onWillUnmount, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { FixField, displayValue } from "./fix_field";

export const MODEL = "fix.screen";

/** The words of a server error, for showing inside the pop-up. */
export function errorText(err) {
    const data = err && (err.data || (err.cause && err.cause.data));
    return (data && (data.message || data.name)) || (err && err.message) || _t("That did not work. Try again.");
}

/** A tiny domain check for "when does this show": [(field, op, value), ...], all must hold. */
export function matches(domain, values) {
    if (!domain || !domain.length) {
        return true;
    }
    const plain = (v) => (Array.isArray(v) ? (v.length && typeof v[0] !== "object" ? v[0] : v.length ? v : false) : v);
    return domain.every((leaf) => {
        if (!Array.isArray(leaf)) {
            return true;
        }
        const [name, op, want] = leaf;
        let have = plain(values[name]);
        if (have === undefined || have === null || have === "") {
            have = false;
        }
        switch (op) {
            case "=":
                return want === false ? !have : have === want;
            case "!=":
                return want === false ? !!have : have !== want;
            case "in":
                return want.includes(have);
            case "not in":
                return !want.includes(have);
            case ">":
                return have > want;
            case "<":
                return have < want;
            default:
                return true;
        }
    });
}

// ====================================================================== the frame
class PopupFrame extends Component {
    static template = "369ai_fix.PopupFrame";
    static components = {};
    static props = ["*"];

    setup() {
        this.onKey = (ev) => {
            if (ev.key === "Escape" && this.props.isTop()) {
                this.props.cancel();
            }
        };
        onMounted(() => document.addEventListener("keydown", this.onKey));
        onWillUnmount(() => document.removeEventListener("keydown", this.onKey));
    }

    get popup() {
        return this.props.entry.popup;
    }

    get wide() {
        return ["checks", "result"].includes(this.popup.kind);
    }

    onBackdrop(ev) {
        if (ev.target === ev.currentTarget) {
            this.props.cancel();
        }
    }
}

// ====================================================================== a wizard / a record / a new record
class PopupForm extends Component {
    static template = "369ai_fix.PopupForm";
    static components = { FixField };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.popupService = useService("fix_popup");
        const p = this.props.popup;
        this.state = useState({ values: { ...(p.values || {}) }, busy: false, error: "" });
    }

    get p() {
        return this.props.popup;
    }

    shown(name) {
        return matches((this.p.show || {})[name], this.state.values);
    }

    buttonShown(button) {
        return matches(button.show, this.state.values);
    }

    infoText(name) {
        return displayValue(this.p.meta[name], this.state.values[name]);
    }

    isHtml(name) {
        return this.p.meta[name] && this.p.meta[name].type === "html";
    }

    isRequired(name) {
        return this.p.meta[name] && this.p.meta[name].required;
    }

    pickFor(name) {
        return (query) => {
            if (this.p.kind === "create") {
                return this.orm.silent.call(MODEL, "screen_pick", [this.p.screen, name, query, this.state.values]);
            }
            return this.orm.silent.call(MODEL, "screen_popup_pick", [this.p.model, name, query, this.state.values]);
        };
    }

    set(name, value) {
        this.state.values[name] = value;
    }

    async press(button) {
        if (this.state.busy) {
            return;
        }
        if (button.confirm && !(await this.popupService.confirm(button.confirm))) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            if (this.p.kind === "create") {
                const vals = {};
                for (const name of this.p.fields) {
                    if (this.state.values[name] !== undefined) {
                        vals[name] = this.state.values[name];
                    }
                }
                const rec = await this.orm.silent.call(MODEL, "screen_save", [this.p.screen, false, vals, this.p.defaults || {}]);
                this.props.finish({ created: rec });
                return;
            }
            const vals = {};
            for (const name of this.p.fields) {
                if (name in this.state.values) {
                    vals[name] = this.state.values[name];
                }
            }
            const outcome = await this.orm.silent.call(MODEL, "screen_popup_submit", [
                this.p.model, this.p.res_id || false, vals, button.name, this.p.context || {},
            ]);
            this.props.outcome(outcome);
        } catch (err) {
            this.state.error = errorText(err);
        } finally {
            this.state.busy = false;
        }
    }
}

// ====================================================================== "Are you sure?"
class PopupConfirm extends Component {
    static template = "369ai_fix.PopupConfirm";
    static props = ["*"];
}

// ====================================================================== Before you start
class ChecksPopup extends Component {
    static template = "369ai_fix.ChecksPopup";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.popupService = useService("fix_popup");
        this.state = useState({ data: null, busy: false, error: "", reason: "", bust: Date.now() });
        onWillStart(() => this.call());
    }

    get visitId() {
        return this.props.popup.visit_id;
    }

    get v() {
        return (this.state.data && this.state.data.view) || null;
    }

    async call(action = null, args = {}) {
        this.state.busy = true;
        this.state.error = "";
        try {
            const data = await this.orm.silent.call(MODEL, "screen_checks", [this.visitId, action, args]);
            this.state.data = data;
            this.state.bust = Date.now();
            if (data.problem) {
                this.state.error = data.problem;
            }
            if (data.started) {
                this.props.outcome({ done: true });
            }
        } catch (err) {
            this.state.error = errorText(err);
        } finally {
            this.state.busy = false;
        }
    }

    tick(item, ev) {
        this.call("check_tick", { item_id: item.id, done: ev.target.checked });
    }

    readFile(ev, then) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const data = String(reader.result || "");
            then(data.slice(data.indexOf(",") + 1), file.name);
        };
        reader.readAsDataURL(file);
    }

    onSafetyPhoto(ev) {
        this.readFile(ev, (data) => this.call("check_safety_photo", { data }));
    }

    onSidePhoto(side, ev) {
        this.readFile(ev, (data) => this.call("check_side_photo", { photo_id: side.id, data }));
    }

    onVideo(ev) {
        this.readFile(ev, (data, name) => this.call("check_video", { data, name }));
    }

    clearSafety() {
        this.call("check_clear_safety");
    }

    photoUrl(id) {
        return `/web/image/fix.visit.check.photo/${id}/image/160x160?unique=${this.state.bust}`;
    }

    start() {
        this.call("start");
    }

    async override() {
        if (!this.state.reason.trim()) {
            this.state.error = _t("Write why work starts without the checks.");
            return;
        }
        if (await this.popupService.confirm(_t("Start work without the checks? Your name and the reason are kept on the visit."))) {
            this.call("override", { reason: this.state.reason });
        }
    }
}

// ====================================================================== What did you find?
const PLANS_HERE = [
    ["now", "Fix now (the part is here)"],
    ["take", "Take the device to the office"],
    ["come_back", "Customer keeps it, we come back"],
];
const PLANS_ORDER = [
    ["keep", "Customer keeps it until the part arrives"],
    ["order_take", "Take the device to the office until the part arrives"],
];

class ResultPopup extends Component {
    static template = "369ai_fix.ResultPopup";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.popupService = useService("fix_popup");
        this.state = useState({
            data: null, busy: false, error: "", note: "", query: "", parts: [], searched: false, brand: "",
            plan: "", days: 3, unit: "days", partDays: 7, acc: {}, noAcc: false,
        });
        onWillStart(async () => {
            await this.call();
            const v = this.v;
            if (v) {
                this.state.note = v.found || "";
                this.state.partDays = v.part_days || 7;
            }
        });
    }

    get v() {
        return (this.state.data && this.state.data.view) || null;
    }

    get plans() {
        return this.v && this.v.to_order ? PLANS_ORDER : PLANS_HERE;
    }

    get needsDays() {
        return ["take", "come_back", "order_take"].includes(this.currentPlan);
    }

    get currentPlan() {
        const keys = this.plans.map((p) => p[0]);
        return keys.includes(this.state.plan) ? this.state.plan : keys[0];
    }

    whereText(line) {
        if (line.status === "in_stock") {
            return _t("In the office (%s)", line.office);
        }
        if (line.status === "other_branch") {
            return _t("At %s", (line.branches || []).map((b) => `${b.name} (${b.qty})`).join(", "));
        }
        return _t("Must be ordered");
    }

    async call(action = null, args = {}) {
        this.state.busy = true;
        this.state.error = "";
        try {
            const data = await this.orm.silent.call(MODEL, "screen_result", [this.props.popup.visit_id, action, args]);
            this.state.data = data;
            if (data.message) {
                this.state.error = data.message;
            }
            if (data.state && data.state !== "in_progress" && action) {
                this.props.outcome({ done: true, message: data.result_label || "" });
            }
            return data;
        } catch (err) {
            this.state.error = errorText(err);
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    saveNote() {
        if (this.v && this.v.stage === "find" && this.state.note !== (this.v.found || "")) {
            this.call("result_note", { note: this.state.note });
        }
    }

    async search(ev) {
        ev && ev.preventDefault();
        const data = await this.call("result_parts", { query: this.state.query });
        this.state.parts = (data && data.parts) || [];
        this.state.searched = true;
    }

    async add(part) {
        if (this.v.need_device && !this.state.brand) {
            this.state.error = _t("Choose the device brand first.");
            return;
        }
        const data = await this.call("result_add_part", {
            product_id: part.product_id, brand_id: Number(this.state.brand) || null,
        });
        if (data && !data.message) {
            this.state.parts = [];
            this.state.query = "";
            this.state.searched = false;
        }
    }

    remove(line) {
        this.call("result_remove_part", { line_id: line.line_id });
    }

    async fixed() {
        if (await this.popupService.confirm(_t("Fixed on the spot? The visit will be closed."))) {
            this.call("result_fixed", { note: this.state.note });
        }
    }

    async quote() {
        const plan = this.currentPlan;
        const days = Number(this.state.days);
        if (this.needsDays && !(this.state.unit === "weeks" ? days >= 1 && days <= 8 : days >= 1 && days <= 60)) {
            this.state.error = _t("How long to fix? 1 to 60 days, or 1 to 8 weeks.");
            return;
        }
        const partDays = Number(this.state.partDays);
        if (this.v.to_order && !(partDays >= 1 && partDays <= 120)) {
            this.state.error = _t("When does the part arrive? Give the days (1 to 120).");
            return;
        }
        if (await this.popupService.confirm(_t("Send the quotation to the customer?"))) {
            this.call("result_quote", { plan, days, unit: this.state.unit, part_days: partDays, note: this.state.note });
        }
    }

    async answer(action, text) {
        if (await this.popupService.confirm(text)) {
            this.call(action);
        }
    }

    take() {
        const ids = Object.keys(this.state.acc).filter((k) => this.state.acc[k]).map(Number);
        if (!this.state.noAcc && !ids.length) {
            this.state.error = _t('Tick what you take with the device, or "Device only".');
            return;
        }
        this.call("result_take", { no_accessories: this.state.noAcc, accessory_ids: this.state.noAcc ? [] : ids });
    }

    money(v) {
        return Number(v || 0).toFixed(3);
    }
}

PopupFrame.components = { PopupForm, PopupConfirm, ChecksPopup, ResultPopup };

// ====================================================================== the service
export const fixPopupService = {
    dependencies: ["orm", "action", "notification", "overlay"],
    start(env, { orm, action, notification, overlay }) {
        const frames = [];

        function show(popup, { onClose, resolve } = {}) {
            const entry = reactive({ popup, version: 0 });
            let closed = false;
            let remove = null;
            const close = (how) => {
                if (closed) {
                    return;
                }
                closed = true;
                remove && remove();
                const at = frames.indexOf(entry);
                if (at >= 0) {
                    frames.splice(at, 1);
                }
                if (resolve) {
                    resolve(how);
                }
            };
            const props = {
                entry,
                isTop: () => frames[frames.length - 1] === entry,
                cancel: () => {
                    close(entry.popup.kind === "confirm" ? false : null);
                    if (entry.popup.kind !== "confirm" && onClose) {
                        onClose();
                    }
                },
                // the pop-up's button answered: another pop-up, done, or somewhere to go
                outcome: (outcome) => {
                    if (outcome && outcome.popup) {
                        entry.popup = outcome.popup;
                        entry.version += 1;
                        return;
                    }
                    close(outcome);
                    handle(outcome, { onClose });
                },
                finish: (value) => close(value),
            };
            frames.push(entry);
            remove = overlay.add(PopupFrame, props, { onRemove: () => (closed = true) });
            return entry;
        }

        async function handle(outcome, { onClose } = {}) {
            if (!outcome) {
                onClose && onClose();
                return;
            }
            if (outcome.message) {
                notification.add(outcome.message, { type: "info" });
            }
            if (outcome.popup) {
                show(outcome.popup, { onClose });
                return;
            }
            if (outcome.open) {
                onClose && onClose();
                await openScreen(outcome.open);
                return;
            }
            if (outcome.action) {
                await action.doAction(outcome.action, { onClose });
                if (outcome.action.type === "ir.actions.act_url" && onClose) {
                    onClose();
                }
                return;
            }
            onClose && onClose();
        }

        async function doAction(act, opts = {}) {
            if (act && typeof act === "object" && act.type === "ir.actions.act_window") {
                let outcome;
                try {
                    outcome = await orm.silent.call(MODEL, "screen_popup_open", [act]);
                } catch (err) {
                    notification.add(errorText(err), { type: "danger" });
                    return;
                }
                return handle(outcome, opts);
            }
            return action.doAction(act, opts);
        }

        function openScreen({ screen, id = false, filter = false, defaults = {}, new: isNew = false } = {}) {
            return action.doAction(`369ai_fix.action_screen_${screen}`, {
                additionalContext: {
                    fix_screen: screen,
                    fix_screen_id: id || false,
                    fix_screen_filter: filter || false,
                    fix_screen_defaults: defaults || {},
                    fix_screen_new: !!isNew,
                },
            });
        }

        function confirm(text, { danger = false, ok = _t("Yes"), cancel = _t("No") } = {}) {
            return new Promise((resolve) => {
                show({ kind: "confirm", text, danger, ok, cancelLabel: cancel }, { resolve: (how) => resolve(!!how) });
            });
        }

        function create(screen, meta, defaults = {}) {
            return new Promise((resolve) => {
                const values = {};
                for (const name of meta.create_fields) {
                    const def = defaults[name];
                    const fieldMeta = meta.fields[name] || {};
                    values[name] = def !== undefined ? def : fieldMeta.type === "boolean" ? false : fieldMeta.type === "many2many" ? [] : false;
                }
                show({
                    kind: "create", screen, title: _t("New: %s", meta.title), fields: meta.create_fields,
                    meta: meta.fields, values, defaults, widgets: meta.widgets || {}, info: [], show: {},
                    buttons: [{ name: "create", label: _t("Create"), kind: "primary", icon: "fa-plus" }],
                }, { resolve: (how) => resolve(how && how.created ? how.created : null) });
            });
        }

        return { doAction, handle, openScreen, confirm, create, show };
    },
};

registry.category("services").add("fix_popup", fixPopupService);
