/** @odoo-module **/

/**
 * One record on a green screen: its header (name, status, buttons), its sections of fields
 * (they save by themselves a moment after typing), its line tables, its live map (visits)
 * and its notes. The Booking Desk shows the same component in its Booking / Job card /
 * Visit tabs, so a record looks and works the same everywhere.
 *
 *   <FixRecord screen="'job_cards'" recordId="7" onChanged="() => reloadList()"/>
 */

import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { FixField, displayValue } from "./fix_field";
import { MODEL, errorText } from "./fix_popup";
import { destroyMap, hasLeaflet, mountMap, updateMap } from "../desk/leaflet_map";

const SAVE_DELAY = 600;
const IMMEDIATE = new Set(["boolean", "selection", "many2one", "many2many", "date", "datetime", "image", "binary"]);

const metaCache = new Map();

/** The screen's config, loaded once per browser tab. */
export async function loadMeta(orm, screen) {
    if (!metaCache.has(screen)) {
        metaCache.set(screen, orm.call(MODEL, "screen_meta", [screen]).catch((err) => {
            metaCache.delete(screen);
            throw err;
        }));
    }
    return metaCache.get(screen);
}

export class FixRecord extends Component {
    static template = "369ai_fix.Record";
    static components = { FixField };
    static props = {
        screen: String,
        recordId: { type: [Number, Boolean], optional: true },
        meta: { type: Object, optional: true },
        onChanged: { type: Function, optional: true },
        onClose: { type: Function, optional: true },
        embedded: { type: Boolean, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.popup = useService("fix_popup");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        this.mapHandle = null;
        this.mapEl = null;
        this.pending = {};
        this.timer = null;
        this.state = useState({
            meta: this.props.meta || null, rec: null, values: {}, status: "", error: "", tab: "",
            busy: "", note: "", newLine: {}, adding: "", options: {},
        });
        onWillStart(() => this.load(this.props));
        onWillUpdateProps(async (next) => {
            if (next.recordId !== this.props.recordId || next.screen !== this.props.screen) {
                await this.flush();
                await this.load(next);
            }
        });
        onWillUnmount(() => {
            this.flush();
            destroyMap(this.mapHandle);
        });
        useEffect(
            () => {
                const el = this.mapRef.el;
                const data = this.state.rec && this.state.rec.extra && this.state.rec.extra.map;
                if (!el || !data) {
                    destroyMap(this.mapHandle);
                    this.mapHandle = null;
                    this.mapEl = null;
                    return;
                }
                if (!this.mapHandle || this.mapEl !== el) {
                    destroyMap(this.mapHandle);
                    this.mapHandle = mountMap(el);
                    this.mapEl = el;
                }
                updateMap(this.mapHandle, data);
            },
            () => [this.mapRef.el, this.state.rec && this.state.rec.extra && this.state.rec.extra.map]
        );
    }

    // ------------------------------------------------------------------ data
    async load(props = this.props) {
        try {
            const meta = props.meta || (await loadMeta(this.orm, props.screen));
            this.state.meta = meta;
            if (!this.state.tab && meta.tabs && meta.tabs.length) {
                this.state.tab = meta.tabs[0];
            }
            await this.loadOptions(meta);
            const rec = await this.orm.silent.call(MODEL, "screen_record", [props.screen, props.recordId || 0]);
            this.setRecord(rec);
            this.state.error = "";
        } catch (err) {
            this.state.error = errorText(err);
        }
    }

    async loadOptions(meta) {
        for (const section of meta.sections) {
            for (const name of section.ticks || []) {
                if (!this.state.options[name]) {
                    this.state.options[name] = await this.orm.silent.call(MODEL, "screen_options", [this.props.screen, name]);
                }
            }
        }
    }

    setRecord(rec) {
        this.state.rec = rec;
        // what is still being typed stays on screen over the server's copy
        this.state.values = { ...rec.values, ...this.pending };
    }

    async reload() {
        const rec = await this.orm.silent.call(MODEL, "screen_record", [this.props.screen, this.recId]);
        this.setRecord(rec);
    }

    get recId() {
        return (this.state.rec && this.state.rec.id) || this.props.recordId || 0;
    }

    get meta() {
        return this.state.meta;
    }

    get settings() {
        return this.meta && this.meta.kind === "settings";
    }

    // ------------------------------------------------------------------ header
    get title() {
        const v = this.state.values;
        if (!this.meta) {
            return "";
        }
        if (this.settings) {
            return this.meta.title;
        }
        const field = this.meta.title_field;
        const value = v[field];
        return (Array.isArray(value) ? value[1] : value) || v.display_name || "";
    }

    get subtitle() {
        const name = this.meta && this.meta.subtitle;
        return name ? displayValue(this.meta.fields[name], this.state.values[name]) : "";
    }

    get badge() {
        const name = this.meta && this.meta.badge;
        return name ? displayValue(this.meta.fields[name], this.state.values[name]) : "";
    }

    get badgeClass() {
        const value = this.meta && this.meta.badge ? this.state.values[this.meta.badge] : "";
        return `fxs-badge fxs-badge-${value || "none"}`;
    }

    get buttons() {
        if (!this.meta || !this.state.rec) {
            return [];
        }
        const allowed = new Set(this.state.rec.buttons || []);
        return this.meta.buttons.filter((b) => {
            if (!allowed.has(b.name)) {
                return false;
            }
            if (b.client === "open") {
                const v = this.state.values[b.field];
                return Array.isArray(v) ? !!v[0] : !!v;
            }
            return true;
        });
    }

    // ------------------------------------------------------------------ sections
    get sections() {
        if (!this.meta) {
            return [];
        }
        return this.meta.sections.filter((s) => !this.meta.tabs.length || !this.state.tab || s.tab === this.state.tab);
    }

    sectionFields(section) {
        return (section.fields || []).filter((f) => this.meta.fields[f]);
    }

    sectionInfo(section) {
        return (section.info || []).filter((f) => this.meta.fields[f] && this.hasValue(f));
    }

    hasValue(name) {
        const meta = this.meta.fields[name];
        const v = this.state.values[name];
        if (meta && meta.type === "boolean") {
            return true;
        }
        return !(v === false || v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length));
    }

    sectionShown(section) {
        if (section.kind === "map") {
            return !!(this.state.rec && this.state.rec.extra && this.state.rec.extra.map);
        }
        if (section.lines) {
            return !!this.meta.fields[section.lines];
        }
        return this.sectionFields(section).length || this.sectionInfo(section).length;
    }

    readonly(name) {
        if (!this.meta.can_write || (this.state.rec && this.state.rec.locked)) {
            return true;
        }
        return this.meta.readonly.includes(name) || !!this.meta.fields[name].readonly;
    }

    label(name) {
        const meta = this.meta.fields[name];
        return meta ? meta.string : name;
    }

    help(name) {
        const meta = this.meta.fields[name];
        return (meta && meta.help) || "";
    }

    info(name) {
        return displayValue(this.meta.fields[name], this.state.values[name], (this.meta.widgets || {})[name]);
    }

    infoHtml(name) {
        return this.meta.fields[name] && this.meta.fields[name].type === "html";
    }

    imageUrl(name) {
        const v = this.state.values;
        return `/web/image/${this.meta.model}/${this.recId}/${name}/240x240?unique=${encodeURIComponent(v.write_date || "")}`;
    }

    pickFor(name) {
        return (query) => this.orm.silent.call(MODEL, "screen_pick", [this.props.screen, name, query, this.state.values]);
    }

    // ------------------------------------------------------------------ saving
    onField(name, value) {
        this.state.values[name] = value;
        this.pending[name] = value;
        const type = (this.meta.fields[name] || {}).type;
        this.state.status = "saving";
        clearTimeout(this.timer);
        if (IMMEDIATE.has(type)) {
            this.flush();
        } else {
            this.timer = setTimeout(() => this.flush(), SAVE_DELAY);
        }
    }

    async flush() {
        clearTimeout(this.timer);
        const vals = this.pending;
        if (!Object.keys(vals).length) {
            return;
        }
        this.pending = {};
        try {
            const rec = await this.orm.silent.call(MODEL, "screen_save", [this.props.screen, this.recId, vals]);
            if (rec && rec.values) {
                this.setRecord(rec);
            }
            this.state.status = Object.keys(this.pending).length ? "saving" : "saved";
            this.state.error = "";
            this.props.onChanged && this.props.onChanged();
        } catch (err) {
            this.pending = { ...vals, ...this.pending };
            this.state.status = "error";
            this.state.error = errorText(err);
        }
    }

    // ------------------------------------------------------------------ buttons
    async press(button) {
        if (this.state.busy) {
            return;
        }
        if (button.client) {
            return this.client(button);
        }
        if (button.confirm && !(await this.popup.confirm(button.confirm))) {
            return;
        }
        await this.flush();
        this.state.busy = button.name;
        this.state.error = "";
        try {
            const outcome = await this.orm.silent.call(MODEL, "screen_button", [this.props.screen, this.recId, button.name]);
            await this.popup.handle(outcome, { onClose: () => this.afterChange() });
        } catch (err) {
            this.state.error = errorText(err);
        } finally {
            this.state.busy = "";
        }
    }

    async afterChange() {
        try {
            await this.reload();
        } catch {
            // the record may be gone (e.g. a wizard deleted it)
        }
        this.props.onChanged && this.props.onChanged();
    }

    client(button) {
        if (button.client === "open") {
            const v = this.state.values[button.field];
            const id = Array.isArray(v) ? v[0] : v;
            return this.popup.openScreen({ screen: button.screen, id });
        }
        if (button.client === "screen") {
            return this.popup.openScreen({ screen: button.screen });
        }
        if (button.client === "desk") {
            return this.env.services.action.doAction("369ai_fix.action_fix_desk", {
                additionalContext: { fix_desk_order_id: this.recId },
            });
        }
        if (button.client === "action") {
            return this.env.services.action.doAction(button.xmlid);
        }
    }

    // ------------------------------------------------------------------ lines
    lineMeta(section) {
        return this.meta.lines[section.lines] || {};
    }

    lineColumns(section) {
        const meta = this.lineMeta(section);
        return (section.columns || []).filter((c) => meta[c]);
    }

    lines(section) {
        return (this.state.rec && this.state.rec.lines[section.lines]) || [];
    }

    lineReadonly(section, column) {
        if (section.readonly || this.readonly(section.lines)) {
            return true;
        }
        if ((section.line_readonly || []).includes(column)) {
            return true;
        }
        return !!(this.lineMeta(section)[column] || {}).readonly;
    }

    lineCanEdit(section) {
        return !section.readonly && !this.readonly(section.lines);
    }

    lineImage(section, line, column) {
        const model = (this.meta.fields[section.lines] || {}).relation;
        return `/web/image/${model}/${line.id}/${column}/96x96?unique=${encodeURIComponent(line.write_date || "")}`;
    }

    linePick(section, column) {
        return (query) => this.orm.silent.call(MODEL, "screen_pick", [this.props.screen, column, query, {}, section.lines]);
    }

    lineTotal(section, column) {
        const meta = this.lineMeta(section)[column] || {};
        if (!["float", "monetary", "integer"].includes(meta.type) || !["subtotal", "price_subtotal"].includes(column)) {
            return "";
        }
        const sum = this.lines(section).reduce((acc, l) => acc + (Number(l[column]) || 0), 0);
        return sum.toLocaleString(undefined, { maximumFractionDigits: 3 });
    }

    async lineCall(section, op, lineId = null, values = null, ids = null) {
        this.state.status = "saving";
        try {
            const rec = await this.orm.silent.call(MODEL, "screen_line", [
                this.props.screen, this.recId, section.lines, op, lineId, values, ids,
            ]);
            this.setRecord(rec);
            this.state.status = "saved";
            this.state.error = "";
            this.props.onChanged && this.props.onChanged();
            return true;
        } catch (err) {
            this.state.status = "error";
            this.state.error = errorText(err);
            return false;
        }
    }

    onLineField(section, line, column, value) {
        line[column] = value;
        const type = (this.lineMeta(section)[column] || {}).type;
        if (IMMEDIATE.has(type)) {
            this.lineCall(section, "update", line.id, { [column]: value });
        } else {
            clearTimeout(line._timer);
            line._timer = setTimeout(() => this.lineCall(section, "update", line.id, { [column]: line[column] }), SAVE_DELAY);
        }
    }

    startAdd(section) {
        this.state.adding = section.lines;
        this.state.newLine = {};
    }

    async saveNewLine(section) {
        const ok = await this.lineCall(section, "add", null, { ...this.state.newLine });
        if (ok) {
            this.state.adding = "";
            this.state.newLine = {};
        }
    }

    async removeLine(section, line) {
        if (await this.popup.confirm(_t("Remove this line?"))) {
            this.lineCall(section, "remove", line.id);
        }
    }

    moveLine(section, line, step) {
        const ids = this.lines(section).map((l) => l.id);
        const at = ids.indexOf(line.id);
        const to = at + step;
        if (to < 0 || to >= ids.length) {
            return;
        }
        [ids[at], ids[to]] = [ids[to], ids[at]];
        this.lineCall(section, "order", null, null, ids);
    }

    openLine(section, line) {
        if (section.open) {
            this.popup.openScreen({ screen: section.open, id: line.id });
        }
    }

    // ------------------------------------------------------------------ notes
    async addNote() {
        const body = this.state.note.trim();
        if (!body) {
            return;
        }
        try {
            const notes = await this.orm.silent.call(MODEL, "screen_note", [this.props.screen, this.recId, body]);
            this.state.rec.notes = notes;
            this.state.note = "";
        } catch (err) {
            this.state.error = errorText(err);
        }
    }

    noteWhen(note) {
        return displayValue({ type: "datetime" }, note.date);
    }

    noteBody(note) {
        return displayValue({ type: "html" }, note.body);
    }

    get hasMap() {
        return hasLeaflet();
    }
}
