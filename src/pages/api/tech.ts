// /api/tech - the technician's link from WhatsApp (v = visit, t = token), for the /tech page:
//   GET  ?v=&t=                                          what the page shows
//   POST {v, t, action: 'ping', lat, lng, accuracy, heading, speed, battery}   the phone's position
//   POST {v, t, action: 'on_the_way' | 'arrive' | 'start' | 'done', lat?, lng?, code?}   one step
import type { APIRoute } from 'astro';
import { hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => String(v ?? '').trim().slice(0, n);
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const ACTIONS = new Set(['ping', 'on_the_way', 'arrive', 'start', 'done']);

export const GET: APIRoute = async ({ request }) => {
  const q = new URL(request.url).searchParams;
  const host = hostOf(request);
  try {
    return json(await odooCall(host, 'fix.service.visit', 'tech_page', { host, ref: s(q.get('v'), 30), token: s(q.get('t'), 100) }));
  } catch (e) {
    console.error('[tech] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};

export const POST: APIRoute = async ({ request }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  const action = s(b.action, 20);
  if (!ACTIONS.has(action)) return json({ ok: false, error: 'unknown action' }, 400);
  const host = hostOf(request);
  try {
    return json(await odooCall(host, 'fix.service.visit', 'tech_page', {
      host, ref: s(b.v, 30), token: s(b.t, 100), action, code: s(b.code, 8),
      lat: num(b.lat), lng: num(b.lng), accuracy: num(b.accuracy),
      heading: num(b.heading), speed: num(b.speed), battery: num(b.battery),
    }));
  } catch (e) {
    console.error('[tech] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
