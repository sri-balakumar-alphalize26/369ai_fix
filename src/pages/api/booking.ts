// POST /api/booking — copy of a booking into Odoo (IT & Mobile Repair > Online Service).
// The customer's WhatsApp message still opens exactly as before; this runs alongside it,
// and any failure here is swallowed so a booking is never blocked by Odoo.
import type { APIRoute } from 'astro';
import { hostOf, ipOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => (typeof v === 'string' ? v.trim().slice(0, n) : '');

export const POST: APIRoute = async ({ request, clientAddress }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => null);
  if (!b || typeof b !== 'object') return json({ ok: false, error: 'bad request' }, 400);
  const lines = Array.isArray(b.lines) ? b.lines.slice(0, 30).map((l: any) => ({
    device: s(l?.device, 80), model: s(l?.model, 80), issue: s(l?.issue, 120), qty: Number(l?.qty) || 1,
  })).filter((l: any) => l.issue) : [];
  if (!lines.length) return json({ ok: false, error: 'nothing booked' }, 400);
  const host = hostOf(request);
  const payload = {
    host,
    ref: s(b.ref, 24),
    mode: ['doorstep', 'pickup'].includes(b.mode) ? b.mode : 'to_confirm',
    source: s(b.source, 20) || 'wizard',
    name: s(b.name, 80),
    phone: s(b.phone, 30),
    email: s(b.email, 120),
    area: s(b.area, 120),
    address: s(b.address, 200),
    lat: typeof b.lat === 'number' ? b.lat : undefined,
    lng: typeof b.lng === 'number' ? b.lng : undefined,
    note: s(b.note, 500),
    coupon: s(b.coupon, 30),
    page: s(b.page, 200),
    ip: ipOf(request, clientAddress),
    lines,
  };
  try {
    const r = await odooCall<{ ok: boolean; ref?: string; error?: string }>(host, 'online.service.order', 'website_create', { payload });
    return json(r, r.ok ? 200 : 422);
  } catch (e) {
    console.error('[booking] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
