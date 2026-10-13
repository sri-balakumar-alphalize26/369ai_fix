// /api/visit - the customer's link from WhatsApp (o = order, t = token), for the
// /slot and /quote pages:
//   GET  ?o=&t=&page=slot|quote          what the page shows
//   POST {o, t, action: 'book', slot_id, date}   pick a visit time
//   POST {o, t, action: 'parts', yes}            order the missing parts? yes / no
//   POST {o, t, action: 'quote', yes}            approve / decline a changed price
import type { APIRoute } from 'astro';
import { hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => String(v ?? '').trim().slice(0, n);

export const GET: APIRoute = async ({ request }) => {
  const q = new URL(request.url).searchParams;
  const host = hostOf(request);
  const method = q.get('page') === 'quote' ? 'quote_options' : 'slot_options';
  try {
    return json(await odooCall(host, 'online.service.order', method, { host, ref: s(q.get('o'), 30), token: s(q.get('t'), 100) }));
  } catch (e) {
    console.error('[visit] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};

export const POST: APIRoute = async ({ request }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  const host = hostOf(request);
  const base = { host, ref: s(b.o, 30), token: s(b.t, 100) };
  try {
    if (b.action === 'book') {
      return json(await odooCall(host, 'online.service.order', 'slot_book',
        { ...base, slot_id: Number(b.slot_id) || 0, date: s(b.date, 10) }));
    }
    if (b.action === 'parts') {
      return json(await odooCall(host, 'online.service.order', 'parts_answer', { ...base, yes: !!b.yes }));
    }
    if (b.action === 'quote') {
      return json(await odooCall(host, 'online.service.order', 'quote_answer', { ...base, yes: !!b.yes }));
    }
    return json({ ok: false, error: 'unknown action' }, 400);
  } catch (e) {
    console.error('[visit] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
