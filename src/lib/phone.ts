// Phone country codes and number-length rules, shared by every phone field on the site
// (booking popup, "book for someone else", track your repair). Lengths are national
// mobile numbers without the country code or a leading 0.
export type Dial = { cc: string; name: string; code: string; len: number; eg: string; start: string };

export const DIAL: Dial[] = [
  { cc: 'om', name: 'Oman', code: '+968', len: 8, eg: '9123 4567', start: '79' },
  { cc: 'in', name: 'India', code: '+91', len: 10, eg: '98765 43210', start: '6789' },
  { cc: 'ae', name: 'UAE', code: '+971', len: 9, eg: '50 123 4567', start: '5' },
  { cc: 'sa', name: 'Saudi Arabia', code: '+966', len: 9, eg: '51 234 5678', start: '5' },
  { cc: 'qa', name: 'Qatar', code: '+974', len: 8, eg: '3312 3456', start: '3567' },
  { cc: 'kw', name: 'Kuwait', code: '+965', len: 8, eg: '5000 1234', start: '569' },
  { cc: 'bh', name: 'Bahrain', code: '+973', len: 8, eg: '3600 1234', start: '36' },
  { cc: 'pk', name: 'Pakistan', code: '+92', len: 10, eg: '301 2345678', start: '3' },
  { cc: 'bd', name: 'Bangladesh', code: '+880', len: 10, eg: '1812 345678', start: '1' },
  { cc: 'lk', name: 'Sri Lanka', code: '+94', len: 9, eg: '71 234 5678', start: '7' },
  { cc: 'np', name: 'Nepal', code: '+977', len: 10, eg: '984 1234567', start: '9' },
  { cc: 'ph', name: 'Philippines', code: '+63', len: 10, eg: '917 123 4567', start: '9' },
  { cc: 'eg', name: 'Egypt', code: '+20', len: 10, eg: '100 123 4567', start: '1' },
  { cc: 'gb', name: 'United Kingdom', code: '+44', len: 10, eg: '7400 123456', start: '7' },
  { cc: 'us', name: 'USA / Canada', code: '+1', len: 10, eg: '201 555 0123', start: '23456789' },
];

export const dialFor = (cc: string | null | undefined): Dial => DIAL.find((d) => d.cc === (cc || '').toLowerCase()) ?? DIAL[0];

/** While typing: drop letters and stop extra digits once the number is full for that country
 *  (a typed country code or leading 0 doesn't count). Returns the cleaned value. */
export function limitPhone(value: string, cc: string): string {
  const d = dialFor(cc), code = d.code.slice(1);
  const v = value.replace(/[^\d+\s-]/g, '').replace(/(?!^)\+/g, '');
  const compact = v.replace(/[\s-]/g, '');
  const prefix = compact.startsWith('+' + code) ? code.length : compact.startsWith('00' + code) ? code.length + 2 : compact.startsWith('0') ? 1 : 0;
  let allowed = d.len + prefix, out = '';
  for (const ch of v) { if (/\d/.test(ch)) { if (allowed <= 0) continue; allowed--; } out += ch; }
  return out.replace(/[\s-]+$/, (m) => (allowed > 0 ? m : ''));
}

/** National digits of what's typed (country code / leading 0 removed); '' if another country's code was typed. */
function national(cc: string, raw: string): string {
  const code = dialFor(cc).code.slice(1);
  let n = raw.replace(/[^\d+]/g, '');
  if (n.startsWith('+' + code)) n = n.slice(code.length + 1);
  else if (n.startsWith('00' + code)) n = n.slice(code.length + 2);
  else if (n.startsWith('+')) return '';
  return n.replace(/^0/, '');
}

const listDigits = (s: string) => (s.length === 1 ? s : s.length > 4 ? `${s[0]} to ${s[s.length - 1]}` : `${s.slice(0, -1).split('').join(', ')} or ${s.slice(-1)}`);

/** Errors we can show while still typing (wrong first digit, one digit repeated). '' when fine so far. */
export function earlyPhoneError(cc: string, raw: string): string {
  const d = dialFor(cc), n = national(cc, raw);
  if (!n) return '';
  if (!d.start.includes(n[0])) return `${d.name} mobile numbers start with ${listDigits(d.start)}.`;
  if (n.length >= 6 && /^(\d)\1+$/.test(n)) return 'Please enter a real mobile number.';
  return '';
}

/** Wire a phone input: limits digits live, shows wrong-start errors at once, "too short" on leaving the box. */
export function bindPhone(input: HTMLInputElement, getCc: () => string, showErr: (msg: string) => void) {
  input.addEventListener('input', () => {
    const cleaned = limitPhone(input.value, getCc());
    if (cleaned !== input.value) input.value = cleaned;
    showErr(earlyPhoneError(getCc(), input.value));
  });
  input.addEventListener('blur', () => {
    if (!input.value.trim()) return;
    const r = checkPhone(getCc(), input.value);
    showErr(r.ok ? '' : r.msg);
  });
}

/** Validate a typed number for a country. Accepts spaces/dashes, an optional country code
 *  or a leading 0. Returns the full international number when valid. */
export function checkPhone(cc: string, raw: string): { ok: boolean; full: string; msg: string } {
  const d = dialFor(cc);
  let n = raw.replace(/[\s\-().]/g, '');
  const code = d.code.replace('+', '');
  if (n.startsWith('+')) {
    if (!n.startsWith('+' + code)) return { ok: false, full: '', msg: `This number doesn't start with ${d.code} (${d.name}). Change the country or remove the code.` };
    n = n.slice(code.length + 1);
  } else if (n.startsWith('00' + code)) n = n.slice(code.length + 2);
  if (n.startsWith('0')) n = n.slice(1);
  if (!/^\d+$/.test(n)) return { ok: false, full: '', msg: 'Use digits only.' };
  const early = earlyPhoneError(cc, raw);
  if (early) return { ok: false, full: '', msg: early };
  if (n.length < d.len) return { ok: false, full: '', msg: `Too short — ${d.name} mobile numbers have ${d.len} digits (you entered ${n.length}).` };
  if (n.length > d.len) return { ok: false, full: '', msg: `Too long — ${d.name} mobile numbers have ${d.len} digits (you entered ${n.length}).` };
  return { ok: true, full: `${d.code} ${n}`, msg: '' };
}
