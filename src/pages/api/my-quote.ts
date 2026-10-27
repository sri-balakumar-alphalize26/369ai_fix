// /api/my-quote - the new price after the technician's check, from My orders, for the signed-in
// customer (the same price page as the WhatsApp link's /quote, proven by their sign-in instead of
// the link's token; Odoo checks the booking is theirs: online.service.order.customer_quote).
//   GET  ?ref=OS/01520                      the lines, the total, the grades to choose, the state
//   POST {ref, yes, choice: [line ids]}     Approve (yes) / Decline, keeping the grades chosen
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
    return json(await odooCall(host, 'online.service.order', 'customer_quote', { host, phone, ...args }));
  } catch (e) {
    console.error('[my-quote] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
}

export const GET: APIRoute = ({ request, cookies }) =>
  call(request, cookies, { ref: s(new URL(request.url).searchParams.get('ref'), 30) });

export const POST: APIRoute = async ({ request, cookies }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  const choice = Array.isArray(b.choice) ? b.choice.filter((x: unknown) => Number.isInteger(x)).slice(0, 20) : [];
  return call(request, cookies, { ref: s(b.ref, 30), action: 'answer', yes: !!b.yes, choice });
};
