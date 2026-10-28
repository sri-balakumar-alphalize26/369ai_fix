/** @odoo-module **/

/**
 * A green screen: every menu of the 369 ai Fix and Fix Website apps opens one of these
 * (client action "369ai_fix.screen", the screen's key in the action's context).
 *
 * Laid out like 369 Mart's desks (its UI kit, @mart369/ui/*, in our green):
 *   head:    the screen's name and what it is for; list / board / week; New
 *   tiles:   the counted filters as number tiles - a tile is a filter
 *   toolbar: every filter as tabs (with their counts), the search box on the right
 *   body:    one full-width card per record; a record opens in a dialog (FixRecord);
 *            'table' screens are edited right in the rows; settings screens are one card
 *
 * What the screen shows comes from fix.screen (app/models/fix_screen.py + its configs).
 */

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { Layout } from "@web/search/layout";
import { Dialog } from "@web/core/dialog/dialog";
import { serializeDate, deserializeDateTime } from "@web/core/l10n/dates";
import { Tabs } from "@mart369/ui/tabs";
import { Search } from "@mart369/ui/search";
import { FixField, displayValue } from "./fix_field";
import { FixRecord, loadMeta } from "./fix_record";
import { MODEL, errorText } from "./fix_popup";

const MAX_TILES = 4;        // the counted filters shown as tiles (369 Mart's desks show four)
const META_COLUMNS = 4;     // values on a card's second line

/** One record, opened from a list card: the record view in a wide dialog. */
export class FixRecordDialog extends Component {
    static template = "369ai_fix.RecordDialog";
    static components = { Dialog, FixRecord };
    static props = ["*"];
}

const { DateTime } = luxon;
const MODE_LABELS = { table: "List", board: "Board", week: "Week" };
const MODE_ICONS = { table: "fa-list", board: "fa-columns", week: "fa-calendar" };

export class FixScreen extends Component {
    static template = "369ai_fix.Screen";
    static components = { Layout, FixRecord, FixField, Tabs, Search };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.popup = useService("fix_popup");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        const ctx = (this.props.action && this.props.action.context) || {};
        const params = (this.props.action && this.props.action.params) || {};
        this.key = params.screen || ctx.fix_screen;
        this.state = useState({
            meta: null, rows: [], total: 0, offset: 0, limit: 40, counts: {}, loading: true, error: "",
            query: "", filter: ctx.fix_screen_filter || params.filter || "", mode: "table", start: "",
            selectedId: ctx.fix_screen_id || params.id || 0, singleId: 0, more: false, saving: {},
        });
        this.searchLater = useDebounced(() => this.load(), 300);
        onWillStart(async () => {
            try {
                const meta = await loadMeta(this.orm, this.key);
                this.state.meta = meta;
                if (!this.state.filter) {
                    this.state.filter = meta.default_filter || (meta.filters[0] && meta.filters[0].key) || "";
                }
                this.state.mode = meta.modes[0] || "table";
                if (meta.kind === "single") {
                    this.state.singleId = await this.orm.call(MODEL, "screen_single", [this.key]);
                } else if (meta.kind !== "settings") {
                    await this.load();
                }
            } catch (err) {
                this.state.error = errorText(err);
            }
            this.state.loading = false;
            if (ctx.fix_screen_new && this.state.meta && this.state.meta.can_create) {
                this.create(ctx.fix_screen_defaults || {});
            } else if (this.state.selectedId && this.kind === "records") {
                // opened on one record (a link from another screen): show it straight away
                this.openRecord(this.state.selectedId);
            }
        });
        onWillUpdateProps(() => {});
    }

    get meta() {
        return this.state.meta;
    }

    get kind() {
        return this.meta ? this.meta.kind : "records";
    }

    // ------------------------------------------------------------------ data
    async load({ append = false } = {}) {
        const s = this.state;
        try {
            const data = await this.orm.silent.call(MODEL, "screen_list", [this.key], {
                query: s.query, filter: s.filter, offset: append ? s.offset + s.limit : 0,
                mode: s.mode, start: s.start || null,
            });
            s.rows = append ? [...s.rows, ...data.rows] : data.rows;
            s.total = data.total;
            s.offset = data.offset;
            s.limit = data.limit;
            s.counts = data.counts || {};
            if (data.start) {
                s.start = data.start;
            }
            s.error = "";
        } catch (err) {
            s.error = errorText(err);
        }
    }

    onQuery(ev) {
        this.onSearch(ev.target.value);
    }

    onSearch(value) {
        this.state.query = value;
        this.searchLater();
    }

    // ------------------------------------------------------------------ tiles and tabs (369 Mart)
    /** The counted filters (not "All"), as number tiles: a tile is a filter. */
    get tiles() {
        if (!this.meta) {
            return [];
        }
        return this.meta.filters
            .filter((f) => f.key !== "all" && this.state.counts[f.key] !== undefined)
            .slice(0, MAX_TILES)
            .map((f) => ({ key: f.key, label: f.label, count: this.state.counts[f.key] }));
    }

    /** Every filter as a tab: [key, label, count] (no count = no badge). */
    get tabItems() {
        return this.meta.filters.map((f) => {
            const n = this.state.counts[f.key];
            return [f.key, f.label, n === undefined ? null : n];
        });
    }

    pickTab(key) {
        if (key !== this.state.filter) {
            this.state.filter = key;
            this.load();
        }
    }

    get modeTabs() {
        return this.meta.modes.map((m) => [m, this.modeLabel(m), null]);
    }

    setFilter(key) {
        this.state.filter = this.state.filter === key && this.meta.default_filter !== key ? this.meta.default_filter : key;
        this.load();
    }

    setMode(mode) {
        this.state.mode = mode;
        this.load();
    }

    loadMore() {
        this.load({ append: true });
    }

    get hasMore() {
        return this.state.mode === "table" && this.state.rows.length < this.state.total;
    }

    // ------------------------------------------------------------------ the list
    columns() {
        return this.meta.columns.filter((c) => c !== this.meta.image);
    }

    label(name) {
        const f = this.meta.fields[name];
        return f ? f.string : name;
    }

    cell(row, name) {
        return displayValue(this.meta.fields[name], row[name], (this.meta.widgets || {})[name]);
    }

    isBadge(name) {
        return name === this.meta.badge;
    }

    badgeClass(row) {
        return `fxs-badge fxs-badge-${row[this.meta.badge] || "none"}`;
    }

    rowClass(row) {
        let cls = "fxs-row";
        if (row.id === this.state.selectedId) {
            cls += " fxs-on";
        }
        if (row.active === false) {
            cls += " fxs-off";
        }
        return cls;
    }

    thumb(row) {
        return `/web/image/${this.meta.model}/${row.id}/${this.meta.image}/96x96?unique=${encodeURIComponent(row.write_date || "")}`;
    }

    rowTitle(row) {
        const v = row[this.meta.title_field];
        return (Array.isArray(v) ? v[1] : v) || row.display_name;
    }

    /** A card's round mark: the first letters of its title. */
    initials(row) {
        const words = String(this.rowTitle(row) || "?").replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/);
        return ((words[0] || "?")[0] + (words.length > 1 ? words[words.length - 1][0] : (words[0] || "")[1] || "")).toUpperCase();
    }

    /** A card's second line: the list's other columns that have a value, "label value". */
    metaLine(row) {
        const skip = new Set([this.meta.title_field, this.meta.badge, this.meta.subtitle, this.meta.image, "display_name"]);
        const out = [];
        for (const c of this.columns()) {
            if (skip.has(c)) {
                continue;
            }
            const value = this.cell(row, c);
            if (value === "" || value === false || value === null || value === undefined) {
                continue;
            }
            out.push({ key: c, label: this.label(c), value });
            if (out.length >= META_COLUMNS) {
                break;
            }
        }
        return out;
    }

    select(row) {
        this.openRecord(row.id);
    }

    openRecord(id) {
        this.state.selectedId = id;
        this.dialog.add(FixRecordDialog, {
            title: this.meta.title,
            screen: this.key,
            recordId: id,
            meta: this.meta,
            onChanged: () => this.onRecordChanged(),
        }, { onClose: () => this.closeRecord() });
    }

    closeRecord() {
        this.state.selectedId = 0;
    }

    onRecordChanged() {
        // the list behind follows quietly
        this.load();
    }

    // board
    get boardColumns() {
        const field = this.meta.fields[this.meta.board];
        const cols = ((field && field.selection) || []).map(([key, label]) => ({ key, label, rows: [] }));
        for (const row of this.state.rows) {
            const col = cols.find((c) => c.key === row[this.meta.board]);
            if (col) {
                col.rows.push(row);
            }
        }
        return cols;
    }

    // week
    get weekDays() {
        const start = this.state.start ? DateTime.fromISO(this.state.start) : DateTime.now().startOf("week");
        const days = [];
        for (let i = 0; i < 7; i++) {
            const day = start.plus({ days: i });
            days.push({ key: day.toISODate(), label: day.toFormat("ccc d LLL"), today: day.hasSame(DateTime.now(), "day"), rows: [] });
        }
        for (const row of this.state.rows) {
            const value = row[this.meta.week];
            if (!value) {
                continue;
            }
            const local = deserializeDateTime(value);
            const d = days.find((x) => x.key === local.toISODate());
            if (d) {
                d.rows.push({ row, time: local.toFormat("HH:mm") });
            }
        }
        for (const d of days) {
            d.rows.sort((a, b) => (a.time < b.time ? -1 : 1));
        }
        return days;
    }

    shiftWeek(step) {
        const start = this.state.start ? DateTime.fromISO(this.state.start) : DateTime.now().startOf("week");
        this.state.start = serializeDate(step ? start.plus({ weeks: step }) : DateTime.now().startOf("week"));
        this.load();
    }

    // table screens: edit right in the row
    get groups() {
        const by = this.meta.group_by;
        if (!by || this.kind !== "table") {
            return [{ key: "", label: "", rows: this.state.rows }];
        }
        const out = [];
        for (const row of this.state.rows) {
            const label = displayValue(this.meta.fields[by], row[by]) || _t("Not set");
            let group = out.find((g) => g.label === label);
            if (!group) {
                group = { key: label, label, rows: [] };
                out.push(group);
            }
            group.rows.push(row);
        }
        return out;
    }

    cellReadonly(name) {
        return !this.meta.can_write || this.meta.readonly.includes(name) || !!(this.meta.fields[name] || {}).readonly;
    }

    pickFor(name, row) {
        return (query) => this.orm.silent.call(MODEL, "screen_pick", [this.key, name, query, row]);
    }

    cellImage(row, name) {
        return `/web/image/${this.meta.model}/${row.id}/${name}/96x96?unique=${encodeURIComponent(row.write_date || "")}`;
    }

    onCell(row, name, value) {
        row[name] = value;
        const type = (this.meta.fields[name] || {}).type;
        clearTimeout(row._timer);
        const save = async () => {
            this.state.saving[row.id] = "saving";
            try {
                const rec = await this.orm.silent.call(MODEL, "screen_save", [this.key, row.id, { [name]: row[name] }]);
                Object.assign(row, rec.values);
                this.state.saving[row.id] = "saved";
            } catch (err) {
                this.state.saving[row.id] = "error";
                this.notification.add(errorText(err), { type: "danger" });
            }
        };
        if (["char", "text", "integer", "float", "monetary"].includes(type)) {
            row._timer = setTimeout(save, 600);
        } else {
            save();
        }
    }

    async move(row, step) {
        const rows = this.state.rows;
        const at = rows.indexOf(row);
        const to = at + step;
        if (to < 0 || to >= rows.length) {
            return;
        }
        [rows[at], rows[to]] = [rows[to], rows[at]];
        try {
            await this.orm.silent.call(MODEL, "screen_resequence", [this.key, rows.map((r) => r.id)]);
        } catch (err) {
            this.notification.add(errorText(err), { type: "danger" });
            this.load();
        }
    }

    async remove(row) {
        if (!(await this.popup.confirm(_t("Delete %s?", this.rowTitle(row))))) {
            return;
        }
        try {
            await this.orm.silent.call(MODEL, "screen_delete", [this.key, row.id]);
            this.load();
        } catch (err) {
            this.notification.add(errorText(err), { type: "danger" });
        }
    }

    // ------------------------------------------------------------------ new
    async create(defaults = {}) {
        const rec = await this.popup.create(this.key, this.meta, defaults);
        if (rec) {
            await this.load();
            if (this.kind === "records") {
                this.openRecord(rec.id);
            }
        }
    }

    modeLabel(mode) {
        return _t(MODE_LABELS[mode] || mode);
    }

    modeIcon(mode) {
        return MODE_ICONS[mode] || "fa-list";
    }

    count(filter) {
        const n = this.state.counts[filter.key];
        return n === undefined ? "" : String(n);
    }
}

registry.category("actions").add("369ai_fix.screen", FixScreen);
