/** @odoo-module **/

/**
 * One field of a green screen or pop-up, drawn by its type: text, number, money, time
 * (float_time), date, date and time, switch, choice, a picker for a link to another record
 * (many2one), tags or ticks (many2many), a picture, or a small rich-text editor (html).
 *
 *   <FixField name="'phone'" meta="meta.fields.phone" value="values.phone"
 *             readonly="false" onChange="(v) => ..." pick="(q) => ..."/>
 *
 * `onChange(value)` gets the server's shape: many2one [id, name] or false, many2many
 * [{id, name}], date "YYYY-MM-DD", datetime "YYYY-MM-DD HH:MM:SS" (UTC), image base64.
 *
 * A date opens the screens' own green calendar (a month of days, Today / Tomorrow / Clear),
 * not the browser's date box, so it looks the same everywhere.
 */

import { Component, markup, onMounted, onWillUpdateProps, useExternalListener, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useDebounced } from "@web/core/utils/timing";
import {
    deserializeDate, deserializeDateTime, formatDate, formatDateTime, serializeDate, serializeDateTime,
} from "@web/core/l10n/dates";

const { DateTime } = luxon;
const WEEKDAYS = [_t("Mo"), _t("Tu"), _t("We"), _t("Th"), _t("Fr"), _t("Sa"), _t("Su")];

export function floatTime(value) {
    const v = Number(value) || 0;
    const sign = v < 0 ? "-" : "";
    const abs = Math.abs(v);
    let h = Math.floor(abs);
    let m = Math.round((abs - h) * 60);
    if (m === 60) {
        h += 1;
        m = 0;
    }
    return `${sign}${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function parseFloatTime(text) {
    const s = String(text || "").trim();
    if (!s) {
        return 0;
    }
    if (s.includes(":")) {
        const [h, m] = s.split(":");
        return (parseInt(h, 10) || 0) + (parseInt(m, 10) || 0) / 60;
    }
    return parseFloat(s.replace(",", ".")) || 0;
}

/** A message's fill-ins as words for the box: {code} -> [Prize code]. */
function tokenWords(text, tokens) {
    let out = String(text || "");
    for (const [code, words] of tokens) {
        out = out.split(`{${code}}`).join(`[${words}]`);
    }
    return out;
}

/** And back, for Odoo and the website: [Prize code] (any case, spaces) -> {code}. */
function tokenCodes(text, tokens) {
    let out = String(text || "");
    for (const [code, words] of tokens) {
        const re = new RegExp(`\\[\\s*${words.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+")}\\s*\\]`, "gi");
        out = out.replace(re, `{${code}}`);
    }
    return out;
}

/** A value as words, for read-only places (lists, info boxes). */
export function displayValue(meta, value, widget) {
    if (!meta) {
        return value === false || value === null || value === undefined ? "" : String(value);
    }
    const type = meta.type;
    if (type === "boolean") {
        return value ? _t("Yes") : _t("No");
    }
    if (value === false || value === null || value === undefined || value === "") {
        return "";
    }
    switch (type) {
        case "many2one":
            return Array.isArray(value) ? value[1] : String(value);
        case "many2many":
            return (value || []).map((v) => v.name).join(", ");
        case "one2many":
            return Array.isArray(value) ? _t("%s lines", value.length) : "";
        case "selection": {
            const found = (meta.selection || []).find((s) => s[0] === value);
            return found ? found[1] : String(value);
        }
        case "date":
            return formatDate(deserializeDate(value));
        case "datetime":
            return formatDateTime(deserializeDateTime(value), { format: "dd MMM yyyy HH:mm" });
        case "float":
        case "monetary":
            if (widget === "float_time") {
                return floatTime(value);
            }
            return Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
        case "integer":
            return String(value);
        case "html":
            return String(value).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
        case "image":
        case "binary":
            return value ? _t("Yes") : "";
        default:
            return String(value);
    }
}

export class FixField extends Component {
    static template = "369ai_fix.Field";
    static props = {
        name: String,
        meta: { type: Object, optional: true },
        value: { optional: true },
        readonly: { type: Boolean, optional: true },
        widget: { type: String, optional: true },
        onChange: { type: Function, optional: true },
        pick: { type: Function, optional: true },
        options: { type: Array, optional: true },
        imageUrl: { type: String, optional: true },
        compact: { type: Boolean, optional: true },
        placeholder: { type: String, optional: true },
        // fill-ins of a message, [[code, words, example]]: the box shows [words], Odoo keeps {code}
        tokens: { type: Array, optional: true },
    };

    setup() {
        this.state = useState({ query: "", results: [], open: false, text: this.textValue(this.props.value),
                                cal: false, month: "" });
        this.editorRef = useRef("editor");
        this.calRef = useRef("cal");
        this.tokRef = useRef("tok");
        // the calendar closes on a click elsewhere, or Escape
        useExternalListener(window, "mousedown", (ev) => {
            if (this.state.cal && this.calRef.el && !this.calRef.el.contains(ev.target)) {
                this.state.cal = false;
            }
        });
        useExternalListener(window, "keydown", (ev) => {
            if (this.state.cal && ev.key === "Escape") {
                ev.stopPropagation();
                this.state.cal = false;
            }
        }, { capture: true });
        this.searchLater = useDebounced(() => this.search(), 250);
        onMounted(() => {
            // the rich-text box is filled once; after that the user's typing is the truth
            if (this.editorRef.el) {
                this.editorRef.el.innerHTML = String(this.props.value || "");
            }
        });
        onWillUpdateProps((next) => {
            // a fresh value from the server, unless the user is typing in this field
            if (next.value !== this.props.value && !this._typing) {
                this.state.text = this.textValue(next.value, next);
            }
        });
    }

    get type() {
        const meta = this.props.meta;
        if (!meta) {
            return "char";
        }
        if (this.props.widget === "float_time") {
            return "float_time";
        }
        return meta.type;
    }

    textValue(value, props = this.props) {
        const meta = props.meta || {};
        if (value === false || value === null || value === undefined) {
            return "";
        }
        if (props.widget === "float_time") {
            return floatTime(value);
        }
        if (meta.type === "many2one") {
            return Array.isArray(value) ? value[1] : "";
        }
        if (props.tokens && props.tokens.length) {
            return tokenWords(String(value), props.tokens);
        }
        return value;
    }

    // ------------------------------------------------------------------ messages with fill-ins
    get tokenPreview() {
        let text = tokenCodes(this.state.text, this.props.tokens || []);
        for (const [code, , example] of this.props.tokens || []) {
            text = text.split(`{${code}}`).join(example || "");
        }
        return text;
    }

    insertToken(tok) {
        const el = this.tokRef.el;
        const add = `[${tok[1]}]`;
        const text = this.state.text || "";
        const at = el && el === document.activeElement ? el.selectionStart : text.length;
        const before = text.slice(0, at), after = text.slice(at);
        const next = before + (before && !/\s$/.test(before) ? " " : "") + add + (after && !/^\s/.test(after) ? " " : "") + after;
        this.state.text = next;
        this.change(tokenCodes(next, this.props.tokens));
        if (el) {
            el.value = next;
            el.focus();
        }
    }

    get display() {
        return displayValue(this.props.meta, this.props.value, this.props.widget);
    }

    get html() {
        return markup(String(this.props.value || ""));
    }

    get selection() {
        return (this.props.meta && this.props.meta.selection) || [];
    }

    get dateInput() {
        const v = this.props.value;
        if (!v) {
            return "";
        }
        if (this.type === "date") {
            return deserializeDate(v).toFormat("yyyy-MM-dd");
        }
        return deserializeDateTime(v).toFormat("yyyy-MM-dd'T'HH:mm");
    }

    // ------------------------------------------------------------------ the green calendar (dates)
    get dateWords() {
        return this.props.value ? deserializeDate(this.props.value).toFormat("ccc dd LLL yyyy") : "";
    }

    get todayIso() {
        return DateTime.local().toISODate();
    }

    get tomorrowIso() {
        return DateTime.local().plus({ days: 1 }).toISODate();
    }

    get calMonth() {
        return DateTime.fromISO(this.state.month || this.todayIso).startOf("month");
    }

    get calTitle() {
        return this.calMonth.toFormat("LLLL yyyy");
    }

    get calWeekdays() {
        return WEEKDAYS;
    }

    /** Six weeks from the Monday on or before the 1st: {iso, d, out (other month), today, on}. */
    get calDays() {
        const first = this.calMonth;
        const start = first.minus({ days: first.weekday - 1 });
        const chosen = this.props.value ? deserializeDate(this.props.value).toISODate() : "";
        const today = this.todayIso;
        return Array.from({ length: 42 }, (_v, i) => {
            const day = start.plus({ days: i });
            const iso = day.toISODate();
            return { iso, d: day.day, out: day.month !== first.month, today: iso === today, on: iso === chosen };
        });
    }

    toggleCal() {
        if (this.props.readonly) {
            return;
        }
        if (!this.state.cal) {
            this.state.month = this.props.value ? deserializeDate(this.props.value).toISODate() : this.todayIso;
        }
        this.state.cal = !this.state.cal;
    }

    moveMonth(step) {
        this.state.month = this.calMonth.plus({ months: step }).toISODate();
    }

    pickDate(iso) {
        this.state.cal = false;
        this.change(iso ? serializeDate(DateTime.fromISO(iso)) : false);
    }

    get tags() {
        return Array.isArray(this.props.value) ? this.props.value : [];
    }

    isTicked(option) {
        return this.tags.some((t) => t.id === option.id);
    }

    // ------------------------------------------------------------------ changes
    change(value) {
        if (this.props.onChange) {
            this.props.onChange(value);
        }
    }

    onText(ev) {
        this._typing = true;
        this.state.text = ev.target.value;
        const type = this.type;
        let value = ev.target.value;
        if (type === "integer") {
            value = parseInt(value, 10) || 0;
        } else if (type === "float" || type === "monetary") {
            value = parseFloat(String(value).replace(",", ".")) || 0;
        } else if (type === "float_time") {
            value = parseFloatTime(value);
        } else if (this.props.tokens && this.props.tokens.length) {
            value = tokenCodes(value, this.props.tokens);   // [Prize code] -> {code}, as the website reads it
        }
        this.change(value);
    }

    onBlur() {
        this._typing = false;
    }

    onToggle(ev) {
        this.change(ev.target.checked);
    }

    onSelect(ev) {
        const raw = ev.target.value;
        const found = this.selection.find((s) => String(s[0]) === raw);
        this.change(found ? found[0] : false);
    }

    onChip(value) {
        if (!this.props.readonly) {
            this.change(value);
        }
    }

    onDate(ev) {
        const raw = ev.target.value;
        if (!raw) {
            this.change(false);
            return;
        }
        if (this.type === "date") {
            this.change(serializeDate(DateTime.fromISO(raw)));
        } else {
            this.change(serializeDateTime(DateTime.fromISO(raw)));
        }
    }

    // many2one / many2many picker
    onQuery(ev) {
        this.state.query = ev.target.value;
        this.state.open = true;
        this.searchLater();
    }

    async search() {
        if (!this.props.pick) {
            return;
        }
        this.state.results = await this.props.pick(this.state.query);
    }

    async openPicker() {
        if (this.props.readonly) {
            return;
        }
        this.state.open = true;
        this.state.query = "";
        await this.search();
    }

    closePicker() {
        // after a click on a result has landed
        setTimeout(() => (this.state.open = false), 180);
    }

    choose(result) {
        this.state.open = false;
        this.state.query = "";
        if (this.type === "many2one") {
            this.state.text = result.name;
            this.change([result.id, result.name]);
        } else if (!this.tags.some((t) => t.id === result.id)) {
            this.change([...this.tags, { id: result.id, name: result.name }]);
        }
    }

    clearOne() {
        this.state.text = "";
        this.change(false);
    }

    removeTag(tag) {
        this.change(this.tags.filter((t) => t.id !== tag.id));
    }

    toggleTick(option, ev) {
        const on = ev.target.checked;
        const rest = this.tags.filter((t) => t.id !== option.id);
        this.change(on ? [...rest, { id: option.id, name: option.name }] : rest);
    }

    // picture
    onFile(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const data = String(reader.result || "");
            this.change(data.slice(data.indexOf(",") + 1));
        };
        reader.readAsDataURL(file);
        ev.target.value = "";
    }

    // small rich text (page bodies)
    exec(command, arg) {
        document.execCommand(command, false, arg || null);
        this.onEditor();
    }

    addLink() {
        const url = window.prompt(_t("Link to (e.g. /services or https://…)"));
        if (url) {
            this.exec("createLink", url);
        }
    }

    onEditor() {
        const el = this.editorRef.el;
        if (el) {
            this._typing = true;
            this.change(el.innerHTML);
        }
    }
}
