// GET /api/my-orders — the logged-in customer's orders with live status (polled by /track).
// DELETE — log out (everywhere: My orders and the account used for booking).
// One sign-in for the whole site: the number signed in on My orders, or the account
// signed in while booking.
import type { APIRoute } from 'astro';
import { clearSession, martFetch, me, secureOf, sessionOf } from '../../lib/account';
import { clearCustomer, customerOf, digits, hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

export const GET: APIRoute = async ({ request, cookies }) => {
  const host = hostOf(request);
  let phone = customerOf(cookies, host);
  if (!phone && sessionOf(cookies)) phone = digits((await me(host, cookies, secureOf(request)).catch(() => null))?.phone);
  if (!phone) return json({ ok: false, login: true }, 401);
  try {
    const r = await odooCall<{ ok: boolean; orders: unknown[]; site?: string }>(host, 'online.service.order', 'customer_orders', { host, phone });
    return json({ ok: !!r.ok, phone, site: r.site ?? '', orders: r.orders ?? [] });
  } catch (e) {
    console.error('[my-orders] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'Order tracking is not available right now.' }, 503);
  }
};

export const DELETE: APIRoute = async ({ request, cookies }) => {
  if (!originOk(request)) return json({ ok: false }, 403);
  const session = sessionOf(cookies);
  if (session) await martFetch(hostOf(request), '/369mart/auth/logout', { method: 'POST', session }).catch(() => null);
  clearSession(cookies);
  clearCustomer(cookies);
  return json({ ok: true });
};
