// Customer accounts: the same accounts as the 369 Mart shop (mart369_auth / mart369_address
// in the same Odoo database), reached through their own /369mart/* routes - nothing of
// 369 Mart is changed. Server-only.
//
// The customer's Odoo session id lives in an httpOnly cookie (`df_session`), as 369 Mart's
// own site keeps `mart_session`. Every call names the database (X-Odoo-Database, from
// ODOO_ROUTES) and the website (X-Fix-Site, so the WhatsApp code says this site's name),
// and passes the visitor's IP on, so Odoo's per-visitor limits see the visitor.
import type { AstroCookies } from 'astro';
import { dbFor, odooUrl } from './odoo';

export const SESSION_COOKIE = 'df_session';
const DAYS = 30;

type Result = { status: number; data: any; session: string | null };

async function freshSession(db: string): Promise<string | null> {
  try {
    const r = await fetch(`${odooUrl()}/web/login?db=${encodeURIComponent(db)}`, {
      redirect: 'manual', signal: AbortSignal.timeout(8000),
    });
    const m = (r.headers.get('set-cookie') || '').match(/session_id=([^;]+)/);
    return m ? m[1] : null;
  } catch {
    return null;
  }
}

/** Call a /369mart/* route. `fresh`: start from a new session bound to the database
 *  (sign-in needs one; a header-only request would not keep the session it makes). */
export async function martFetch(host: string, path: string, opts: {
  method?: string; body?: unknown; session?: string | null; fresh?: boolean; ip?: string;
} = {}): Promise<Result> {
  const db = dbFor(host);
  if (!db) return { status: 503, data: { ok: false, error: 'Accounts are not connected for this website.' }, session: null };
  let started: string | null = null;
  if (opts.fresh && !opts.session) {
    started = await freshSession(db);
    if (!started) return { status: 503, data: { ok: false, error: "Can't reach our server. Try again in a moment." }, session: null };
  }
  const sent = opts.session || started;
  const headers: Record<string, string> = {
    'content-type': 'application/json', accept: 'application/json',
    'x-odoo-database': db, 'x-fix-site': host,
  };
  if (sent) headers.cookie = `session_id=${sent}`;
  if (opts.ip) headers['x-forwarded-for'] = opts.ip;
  let r: Response;
  try {
    r = await fetch(odooUrl() + path, {
      method: opts.method || 'GET', headers, redirect: 'manual',
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    return { status: 503, data: { ok: false, error: "Can't reach our server. Try again in a moment." }, session: null };
  }
  const m = (r.headers.get('set-cookie') || '').match(/session_id=([^;]+)/);
  let data: any = null;
  try { data = await r.json(); } catch { /* not JSON */ }
  let status = r.status;
  if (status >= 300 && status < 400) {
    // A route that needs a signed-in customer redirects to the login page: signed out.
    status = 401;
    data = { ok: false, error: 'Please sign in again.' };
  } else if (status === 403 && opts.session && !data) {
    status = 401;
    data = { ok: false, error: 'Please sign in again.' };
  }
  return { status, data: data || { ok: false }, session: m ? m[1] : started };
}

export function setSession(cookies: AstroCookies, value: string, secure: boolean) {
  cookies.set(SESSION_COOKIE, value, { httpOnly: true, sameSite: 'lax', secure, path: '/', maxAge: DAYS * 86400 });
}

export function clearSession(cookies: AstroCookies) {
  cookies.delete(SESSION_COOKIE, { path: '/' });
}

export const sessionOf = (cookies: AstroCookies) => cookies.get(SESSION_COOKIE)?.value || null;

export const secureOf = (request: Request) =>
  new URL(request.url).protocol === 'https:' || request.headers.get('x-forwarded-proto') === 'https';

/** A call as the signed-in customer. Odoo gives a signed-in session a new id every 3 hours
 *  and stops taking the old one 2 minutes later, so the new id is kept (for another 30 days,
 *  as 369 Mart's own site does) - otherwise the customer would be signed out after 3 hours.
 *  A signed-out answer drops the cookie; Odoo not answering keeps it. */
export async function martAs(host: string, path: string, cookies: AstroCookies, secure: boolean,
  opts: { method?: string; body?: unknown; ip?: string } = {}): Promise<Result> {
  const session = sessionOf(cookies);
  if (!session) return { status: 401, data: { ok: false, error: 'Please sign in.' }, session: null };
  const r = await martFetch(host, path, { ...opts, session });
  if (r.status === 401) clearSession(cookies);
  else if (r.status < 400 && r.session && r.session !== session) setSession(cookies, r.session, secure);
  return r;
}

/** The signed-in customer ({partner_id, name, phone, email}) or null. */
export async function me(host: string, cookies: AstroCookies, secure = false): Promise<any | null> {
  if (!sessionOf(cookies)) return null;
  const r = await martAs(host, '/369mart/auth/me', cookies, secure);
  return r.status === 200 && r.data?.ok ? r.data : null;
}
