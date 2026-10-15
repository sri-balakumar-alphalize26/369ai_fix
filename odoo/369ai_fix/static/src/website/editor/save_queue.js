/** @odoo-module */
/**
 * How the Fix Website editor saves: a change shows at once, is written a moment after
 * typing stops (one write per record, not one per keystroke), and the screen then reloads
 * from the server so what is drawn is always what the website would receive.
 *
 *   const save = useSaveQueue({ orm, notification, reload, onStatus, find });
 *   save.edit("fix.home.section", rec, "title", value);   // debounced write
 *   save.run(() => orm.unlink(model, [id]));              // anything that is not a field edit
 */
import { onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useDebounced } from "@web/core/utils/timing";

export function useSaveQueue({ orm, notification, reload, onStatus, find, delay = 600 }) {
    const pending = new Map();   // "model:id" -> { model, id, vals }
    const status = (s) => onStatus && onStatus(s);
    let busy = false;            // one write at a time, so a reload never lands over newer edits

    async function _flush() {
        if (!pending.size) {
            return;
        }
        if (busy) {
            flush();
            return;
        }
        busy = true;
        const batch = [...pending.values()];
        pending.clear();
        try {
            for (const { model, id, vals } of batch) {
                await orm.write(model, [id], vals);
            }
            await reload();
            status(pending.size ? "saving" : "saved");
        } catch (err) {
            // keep the typed values on screen and try again on the next edit
            for (const entry of batch) {
                const key = `${entry.model}:${entry.id}`;
                const queued = pending.get(key);
                pending.set(key, queued ? { ...queued, vals: { ...entry.vals, ...queued.vals } } : entry);
            }
            status("error");
            notification.add(_t("That change could not be saved."), { type: "danger" });
            throw err;
        } finally {
            busy = false;
        }
    }

    const flush = useDebounced(_flush, delay, { execBeforeUnmount: true });

    function flushNow() {
        flush.cancel();
        return _flush();
    }

    /** Put edits still in flight back on top of freshly loaded data. */
    function applyPending() {
        if (!find) {
            return;
        }
        for (const { model, id, vals } of pending.values()) {
            const rec = find(model, id);
            if (rec) {
                Object.assign(rec, vals);
            }
        }
    }

    /** Change a field on screen now, write it shortly ({ now: true } = write at once, for switches;
     *  { as: 'server_field' } when the screen's name differs from the record's). */
    function edit(model, rec, field, value, { now = false, as = null } = {}) {
        rec[field] = value;
        const key = `${model}:${rec.id}`;
        const entry = pending.get(key) || { model, id: rec.id, vals: {} };
        entry.vals[as || field] = value;
        pending.set(key, entry);
        status("saving");
        return now ? flushNow().catch(() => {}) : flush();
    }

    function valueFrom(ev) {
        const el = ev.target;
        if (el.type === "checkbox") {
            return el.checked;
        }
        if (el.type === "number") {
            const n = parseFloat(el.value);
            return Number.isFinite(n) ? n : 0;
        }
        return el.value;
    }

    /** A server change that is not a field edit (add, remove, reorder), then reload. */
    async function run(fn, { successMessage } = {}) {
        status("saving");
        try {
            await flushNow();
            const result = await fn();
            await reload();
            status("saved");
            if (successMessage) {
                notification.add(successMessage, { type: "success" });
            }
            return result;
        } catch (err) {
            status("error");
            notification.add(_t("That change could not be saved."), { type: "danger" });
            throw err;
        }
    }

    onWillUnmount(() => flush.cancel(true));

    return { edit, run, flush, flushNow, applyPending, valueFrom, pending };
}
