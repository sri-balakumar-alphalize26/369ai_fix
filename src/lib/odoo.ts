// Server-only bridge to Odoo (module 369ai_fix_customer_module).
//
// Which database? Chosen by the host the visitor used, so one copy of this site can
// serve several domains, each feeding its own Odoo database:
//   ODOO_ROUTES=danatfix.com,www.danatfix.com=DUBAI_TEST;369aifix.com=OTHER_DB
//   ODOO_DB=DUBAI_TEST                    (fallback when no route matches)
//   ODOO_API_KEY=...                      (bot user's key; per database: ODOO_KEY_OTHER_DB=...)
//   ODOO_URL=http://127.0.0.1:8069
// The Odoo side only accepts hosts listed in its own Online Service > Configuration > Websites.
// Nothing here ever reaches the browser.
import { createHmac, timingSafeEqual } from 'node:crypto';
import type { AstroCookies } from 'astro';

const env = (k: string) => (import.meta.env as Record<string, string | undefined>)[k] ?? process.env[k];

// The Host header as the visitor typed it (the Cloudflare tunnel passes it through).
// request.url is not used: Astro's standalone server may build it as localhost.
export const hostOf = (request: Request) => {
  const h = (request.headers.get('host') || '').trim().toLowerCase().replace(/:\d+$/, '');
  if (h) return h;
  try { return new URL(request.url).hostname.toLowerCase(); } catch { return ''; }
};

export const ipOf = (request: Request, socket?: string) =>
  request.headers.get('cf-connecting-ip') || request.headers.get('x-forwarded-for')?.split(',')[0].trim() || socket || '';

/** The Odoo database (and its key) for this host, or null when this host is not connected. */
export function targetFor(host: string): { db: string; key: string } | null {
  let db = '';
  for (const part of (env('ODOO_ROUTES') || '').split(';')) {
    const [hosts, name] = part.split('=');
    if (!hosts || !name) continue;
    if (hosts.split(',').map((h) => h.trim().toLowerCase()).includes(host)) { db = name.trim(); break; }
  }
  db = db || env('ODOO_DB') || '';
  const key = env(`ODOO_KEY_${db.toUpperCase().replace(/[^A-Z0-9]/g, '_')}`) || env('ODOO_API_KEY') || '';
  return db && key ? { db, key } : null;
}

/** POST /json/2/<model>/<method>. Throws on HTTP or Odoo errors; 8 s timeout. */
export async function odooCall<T = any>(host: string, model: string, method: string, args: Record<string, unknown>): Promise<T> {
  const t = targetFor(host);
  if (!t) throw new Error('odoo not configured for ' + host);
  const base = (env('ODOO_URL') || 'http://127.0.0.1:8069').replace(/\/$/, '');
  const r = await fetch(`${base}/json/2/${model}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `bearer ${t.key}`, 'x-odoo-database': t.db },
    body: JSON.stringify(args),
    signal: AbortSignal.timeout(8000),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`odoo ${r.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text) as T;
}

// ---- customer session after the WhatsApp code: signed, http-only cookie ----
const COOKIE = 'df_cust';
const DAYS = 30;
const secret = () => env('ADMIN_SECRET') || env('ODOO_API_KEY') || 'df-customer';
const sign = (data: string) => createHmac('sha256', secret()).update(data).digest('base64url');

export function setCustomer(cookies: AstroCookies, phone: string, host: string, secure: boolean) {
  const exp = Date.now() + DAYS * 86400 * 1000;
  const data = Buffer.from(JSON.stringify({ p: phone, h: host, e: exp })).toString('base64url');
  cookies.set(COOKIE, `${data}.${sign(data)}`, { httpOnly: true, sameSite: 'lax', secure, path: '/', maxAge: DAYS * 86400 });
}

export function clearCustomer(cookies: AstroCookies) {
  cookies.delete(COOKIE, { path: '/' });
}

/** The logged-in customer's phone digits for THIS host, or ''. */
export function customerOf(cookies: AstroCookies, host: string): string {
  const raw = cookies.get(COOKIE)?.value || '';
  const [data, sig] = raw.split('.');
  if (!data || !sig) return '';
  const want = Buffer.from(sign(data)), got = Buffer.from(sig);
  if (want.length !== got.length || !timingSafeEqual(want, got)) return '';
  try {
    const v = JSON.parse(Buffer.from(data, 'base64url').toString());
    return v.h === host && v.e > Date.now() && typeof v.p === 'string' ? v.p : '';
  } catch { return ''; }
}

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });

export const digits = (v: unknown) => String(v ?? '').replace(/\D/g, '').slice(0, 15);
