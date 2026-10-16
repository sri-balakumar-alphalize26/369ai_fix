/** @odoo-module **/

/**
 * The alarms of the 369 ai Fix app, in one place.
 *
 * Web Audio, no sound file to fail to load. Three tones, so a counter who hears
 * one without looking knows which it is:
 *
 *  - NEW_TONE    rising three-note chime: a website booking waits for review
 *  - SLOT_TONE   falling two-note "ding-dong": a customer booked the visit time
 *  - ORDER_TONE  two-tone siren: the plain Online Service alarm (new, unopened order)
 *
 * While the Booking Desk is open in a tab it owns the sound (`deskIsOpen()`): the
 * background services on the other pages stay quiet so two copies of the same
 * alarm never beat against each other. The desk sets `document.body.dataset.fixDesk`
 * while it is mounted; the services only read it.
 */

export const NEW_TONE = { notes: [784, 988, 1175], step: 0.22, len: 0.18, gap: 0.5, type: "square" };
export const SLOT_TONE = { notes: [1047, 698], step: 0.42, len: 0.36, gap: 0.9, type: "sine" };
export const ORDER_TONE = { notes: [880, 660], step: 0.36, len: 0.32, gap: 0, type: "triangle" };

export function deskIsOpen() {
    return document.body.dataset.fixDesk === "1";
}

export function setDeskOpen(open) {
    if (open) {
        document.body.dataset.fixDesk = "1";
    } else {
        delete document.body.dataset.fixDesk;
    }
}

export class FixAlarm {
    constructor() {
        this.ctx = null;
        this.armed = false;
        this._timer = null;
    }

    /** Browsers only play sound after a click or key press: call this from one. */
    async arm() {
        if (this.armed) {
            return true;
        }
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) {
            return false;
        }
        this.ctx = this.ctx || new Ctx();
        try {
            await this.ctx.resume();
        } catch {
            // the state below tells the truth
        }
        this.armed = this.ctx.state === "running";
        return this.armed;
    }

    _tone(freq, at, length, type) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = type || "square";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.7, at + 0.01);
        gain.gain.setValueAtTime(0.7, at + length - 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + length);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(at);
        osc.stop(at + length + 0.02);
    }

    /** Ring `tone` for `seconds`, scheduled a second ahead at a time so stop() is instant. */
    ring(seconds, tone = NEW_TONE) {
        this.stop();
        if (!this.armed || !this.ctx) {
            return;
        }
        const t = tone;
        const end = this.ctx.currentTime + seconds;
        let next = this.ctx.currentTime + 0.05;
        let i = 0;
        const schedule = () => {
            const horizon = this.ctx.currentTime + 1.0;
            while (next < horizon && next < end) {
                this._tone(t.notes[i % t.notes.length], next, t.len, t.type);
                i += 1;
                next += i % t.notes.length === 0 ? t.step + t.gap : t.step;
            }
            if (next >= end) {
                this.stop();
            }
        };
        schedule();
        this._timer = setInterval(schedule, 400);
    }

    stop() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }
}

/**
 * Ring `tone` for `ring` seconds, pause `repeat` seconds, again - until stop().
 * One of these per alarm; `start()` is harmless while it already runs.
 */
export class AlarmLoop {
    constructor(alarm, tone) {
        this.alarm = alarm;
        this.tone = tone;
        this._timer = null;
        this._delay = null;
    }

    get running() {
        return !!(this._timer || this._delay);
    }

    start(ring, repeat, delayMs = 0) {
        if (this.running) {
            return;
        }
        const cycle = (ring + repeat) * 1000;
        const go = () => {
            this._delay = null;
            this.alarm.ring(ring, this.tone);
            this._timer = setInterval(() => this.alarm.ring(ring, this.tone), cycle);
        };
        if (delayMs > 0) {
            this._delay = setTimeout(go, delayMs);
        } else {
            go();
        }
    }

    stop() {
        if (this._delay) {
            clearTimeout(this._delay);
            this._delay = null;
        }
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
        this.alarm.stop();
    }
}
