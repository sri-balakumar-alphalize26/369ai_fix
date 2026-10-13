/** @odoo-module **/

/**
 * The website-booking alarm, shared by the Live Screen and the background
 * service that rings on every other page.
 *
 * Same idea as the Store's own alarm (Web Audio, no sound file to fail to
 * load), kept as a copy here so this module does not break when the Store
 * module moves its code around. The tone is deliberately different from the
 * order and enquiry alarms: a counter that hears three alarms has to tell
 * them apart without looking.
 */

/** Rising three-note chime, quicker than the order alarm. */
export const BOOKING_TONE = { notes: [784, 988, 1175], step: 0.22, len: 0.18, gap: 0.5 };

/**
 * The second alarm: a customer booked the visit time. Falling two-note "ding-dong",
 * slower and lower, so it is never mistaken for a new booking.
 */
export const SLOT_TONE = { notes: [1047, 698], step: 0.42, len: 0.36, gap: 0.9, type: "sine" };

export class BookingAlarm {
    constructor() {
        this.ctx = null;
        this.armed = false;
        this._timer = null;
    }

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
            // state below tells the truth
        }
        this.armed = this.ctx.state === "running";
        return this.armed;
    }

    _tone(freq, at, length, type = "square") {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = type;
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

    /** Ring for `seconds`, scheduled a second ahead at a time so stop() is instant. */
    ring(seconds, tone = BOOKING_TONE) {
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
                this._tone(t.notes[i % t.notes.length], next, t.len, t.type || "square");
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
 * How many Live Screens are open in this tab. While one is open it owns the
 * sound; the background service stays quiet so two copies of the same alarm
 * do not beat against each other.
 */
export const presence = { screens: 0 };
