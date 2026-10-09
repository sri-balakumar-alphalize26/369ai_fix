// Admin login for /admin and the ?admin= pop-up on Home (server only).
// ID and password are set here in code on the manager's request — change them here to change the login.
// They are only ever checked on the server; the browser never sees them.
// After login the browser gets a signed, http-only cookie valid for 8 hours.
import { createHmac, timingSafeEqual } from 'node:crypto';
import type { AstroCookies } from 'astro';

const COOKIE = 'df_admin';
const HOURS = 8;
const env = (k: string) => (import.meta.env as Record<string, string | undefined>)[k] ?? process.env[k];

const ADMIN_ID = 'Alphalize';
const ADMIN_PASSWORD = 'DanatFix1';
// Secret door: only the Home link ?admin=danatfix1 opens the admin pop-up (any letter case)
const ADMIN_LINK_KEY = 'danatfix1';
export const gateOk = (key: string | null | undefined) => !!key && safeEqual(key.trim().toLowerCase(), ADMIN_LINK_KEY);
export const adminId = () => ADMIN_ID;
export const adminPassword = () => ADMIN_PASSWORD;
const secret = () => env('ADMIN_SECRET') || `df:${adminPassword()}`; // changing the password logs everyone out

const sign = (data: string) => createHmac('sha256', secret()).update(data).digest('base64url');

function safeEqual(a: string, b: string) {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

// ---- brute-force protection: 5 wrong tries → 15 minute lock, per IP ----
const fails = new Map<string, { n: number; until: number }>();
export function isLockedOut(ip: string) {
  const f = fails.get(ip);
  return !!f && f.until > Date.now();
}
function noteFail(ip: string) {
  const f = fails.get(ip) ?? { n: 0, until: 0 };
  f.n += 1;
  if (f.n >= 5) { f.until = Date.now() + 15 * 60 * 1000; f.n = 0; }
  fails.set(ip, f);
}

/** Check ID + password; on success set the login cookie. The ID ignores upper/lower case. */
export function login(id: string, password: string, ip: string, cookies: AstroCookies, secure: boolean): 'ok' | 'wrong' | 'locked' | 'not-configured' {
  if (!adminPassword()) return 'not-configured';
  if (isLockedOut(ip)) return 'locked';
  const idOk = safeEqual(id.trim().toLowerCase(), adminId().toLowerCase());
  const pwOk = safeEqual(password, adminPassword());
  if (!idOk || !pwOk) { noteFail(ip); return 'wrong'; }
  fails.delete(ip);
  const exp = String(Date.now() + HOURS * 3600 * 1000);
  cookies.set(COOKIE, `${exp}.${sign(exp)}`, { httpOnly: true, sameSite: 'strict', secure, path: '/', maxAge: HOURS * 3600 });
  return 'ok';
}

export function logout(cookies: AstroCookies) {
  cookies.delete(COOKIE, { path: '/' });
}

/** True if the request carries a valid, unexpired login cookie. */
export function isAdmin(cookies: AstroCookies): boolean {
  if (!adminPassword()) return false;
  const v = cookies.get(COOKIE)?.value;
  if (!v) return false;
  const [exp, mac] = v.split('.');
  if (!exp || !mac || !/^\d+$/.test(exp) || Number(exp) < Date.now()) return false;
  return safeEqual(mac, sign(exp));
}

/** Reject form posts that come from another website (CSRF). */
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get('origin');
  if (!origin) return true; // same-site form posts from older browsers
  try { return new URL(origin).host === new URL(request.url).host; } catch { return false; }
}
