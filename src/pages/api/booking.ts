// POST /api/booking - a booking into Odoo (IT & Mobile Repair > Online Service), which makes
// the job card. Signed in (369 Mart account): the customer and their chosen saved address come
// from the account. Not signed in (Odoo was down when the page loaded): name/phone/area as
// before, and the customer's WhatsApp message still opens either way - a booking is never lost.
// Answers {ok, ref, upload_token} - the token lets /api/booking-media add the photos.
import type { APIRoute } from 'astro';
import { me, secureOf } from '../../lib/account';
import { hostOf, ipOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => (typeof v === 'string' ? v.trim().slice(0, n) : '');
const id = (v: unknown) => (Number.isInteger(v) && (v as number) > 0 ? (v as number) : undefined);

export const POST: APIRoute = async ({ request, clientAddress, cookies }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => null);
  if (!b || typeof b !== 'object') return json({ ok: false, error: 'bad request' }, 400);
  const lines = Array.isArray(b.lines) ? b.lines.slice(0, 30).map((l: any) => ({
    device: s(l?.device, 80), model: s(l?.model, 80), issue: s(l?.issue, 120), qty: Number(l?.qty) || 1,
    category_id: id(l?.category_id), brand_id: id(l?.brand_id), series_id: id(l?.series_id),
    model_id: id(l?.model_id), product_id: id(l?.product_id),
  })).filter((l: any) => l.issue || l.product_id) : [];
  if (!lines.length) return json({ ok: false, error: 'nothing booked' }, 400);
  const host = hostOf(request);
  const who = await me(host, cookies, secureOf(request)).catch(() => null);
  const payload: Record<string, unknown> = {
    host,
    ref: s(b.ref, 24),
    mode: ['doorstep', 'pickup'].includes(b.mode) ? b.mode : 'to_confirm',
    source: s(b.source, 20) || 'wizard',
    name: s(b.name, 80) || who?.name || '',
    phone: s(b.phone, 30) || who?.phone || '',
    email: s(b.email, 120) || who?.email || '',
    area: s(b.area, 120),
    address: s(b.address, 200),
    lat: typeof b.lat === 'number' ? b.lat : undefined,
    lng: typeof b.lng === 'number' ? b.lng : undefined,
    note: s(b.note, 500),
    problem: s(b.problem, 1000),
    coupon: s(b.coupon, 30),
    page: s(b.page, 200),
    ip: ipOf(request, clientAddress),
    lines,
  };
  if (who?.partner_id) {
    payload.partner_id = who.partner_id;            // checked by the session, not by the browser
    payload.address_id = id(b.address_id);          // Odoo checks it is this customer's address
  }
  try {
    // 30 s: Odoo also makes the job cards and WhatsApps the customer before it answers, and a
    // slow WhatsApp gateway alone can take several seconds. Giving up early would tell the
    // customer "couldn't send" for a booking that was in fact saved.
    const r = await odooCall<{ ok: boolean; ref?: string; error?: string; upload_token?: string }>(
      host, 'online.service.order', 'website_create', { payload }, 30000);
    return json(r, r.ok ? 200 : 422);
  } catch (e) {
    console.error('[booking] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
