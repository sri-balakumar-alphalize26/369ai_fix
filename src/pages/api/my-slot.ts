// /api/my-slot - Pick a time from My orders, for the signed-in customer (the same slot page as
// the WhatsApp link, proven by their sign-in instead of the link's token; Odoo checks the booking
// is theirs: online.service.order.customer_slot).
//   GET  ?ref=OS/01171                          the estimate, the state and the free windows
//   POST {ref, action: 'book', slot_id, date}   pick / change the time
//   POST {ref, action: 'parts', yes}            order the missing part? yes / no
import type { APIRoute } from 'astro';
import { me, secureOf, sessionOf } from '../../lib/account';
import { customerOf, digits, hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => String(v ?? '').trim().slice(0, n);

// the signed-in number, as /api/my-orders reads it (never from the page)
async function phoneOf(request: Request, cookies: any, host: string) {
  let phone = customerOf(cookies, host);
  if (!phone && sessionOf(cookies)) phone = digits((await me(host, cookies, secureOf(request)).catch(() => null))?.phone);
  return phone;
}

async function call(request: Request, cookies: any, args: Record<string, unknown>) {
  const host = hostOf(request);
  const phone = await phoneOf(request, cookies, host);
  if (!phone) return json({ ok: false, error: 'sign in' }, 401);
  try {
    return json(await odooCall(host, 'online.service.order', 'customer_slot', { host, phone, ...args }));
  } catch (e) {
    console.error('[my-slot] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
}

export const GET: APIRoute = ({ request, cookies }) =>
  call(request, cookies, { ref: s(new URL(request.url).searchParams.get('ref'), 30) });

export const POST: APIRoute = async ({ request, cookies }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  if (b.action === 'book') return call(request, cookies, { ref: s(b.ref, 30), action: 'book', slot_id: Number(b.slot_id) || 0, date: s(b.date, 10) });
  if (b.action === 'parts') return call(request, cookies, { ref: s(b.ref, 30), action: 'parts', yes: !!b.yes });
  return json({ ok: false, error: 'unknown action' }, 400);
};
