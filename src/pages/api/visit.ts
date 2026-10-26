// /api/visit - the customer's link from WhatsApp (o = order, t = token), for the
// /slot and /quote pages, and the rating link (v = visit, t = token) for /rate:
//   GET  ?o=&t=&page=slot|quote          what the page shows
//   GET  ?v=&t=&page=rate                the visit to rate
//   POST {o, t, action: 'book', slot_id, date}   pick a visit time
//   POST {o, t, action: 'parts', yes}            order the missing parts? yes / no
//   POST {o, t, action: 'quote', yes, choice?}   approve / decline a changed price (choice: the grade kept
//                                                where a part was offered in two)
//   POST {v, t, action: 'rate', stars, note?}    rate the visit (once)
import type { APIRoute } from 'astro';
import { hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => String(v ?? '').trim().slice(0, n);

export const GET: APIRoute = async ({ request }) => {
  const q = new URL(request.url).searchParams;
  const host = hostOf(request);
  try {
    if (q.get('page') === 'rate') {
      return json(await odooCall(host, 'fix.service.visit', 'rate_options', { host, ref: s(q.get('v'), 30), token: s(q.get('t'), 100) }));
    }
    const method = q.get('page') === 'quote' ? 'quote_options' : 'slot_options';
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
      const choice = Array.isArray(b.choice) ? b.choice.filter((x: unknown) => Number.isInteger(x)).slice(0, 20) : [];
      return json(await odooCall(host, 'online.service.order', 'quote_answer', { ...base, yes: !!b.yes, choice }));
    }
    if (b.action === 'rate') {
      return json(await odooCall(host, 'fix.service.visit', 'rate_answer',
        { host, ref: s(b.v, 30), token: s(b.t, 100), stars: Number(b.stars) || 0, note: s(b.note, 1000) }));
    }
    return json({ ok: false, error: 'unknown action' }, 400);
  } catch (e) {
    console.error('[visit] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
