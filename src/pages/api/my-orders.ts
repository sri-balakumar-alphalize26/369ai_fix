// GET /api/my-orders — the logged-in customer's orders with live status (polled by /track).
// DELETE — log out.
import type { APIRoute } from 'astro';
import { sameOrigin } from '../../lib/adminAuth';
import { clearCustomer, customerOf, hostOf, json, odooCall } from '../../lib/odoo';

export const prerender = false;

export const GET: APIRoute = async ({ request, cookies }) => {
  const host = hostOf(request);
  const phone = customerOf(cookies, host);
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
  if (!sameOrigin(request)) return json({ ok: false }, 403);
  clearCustomer(cookies);
  return json({ ok: true });
};
