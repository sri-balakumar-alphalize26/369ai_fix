// /api/spin - Spin & Win, for the signed-in customer only (the wheel asks them to sign in with
// the WhatsApp code first, as the booking does). The customer and their phone come from the
// session, never from the page, so a spin is always a verified number. Odoo picks the prize
// and keeps the win on the customer's contact (odoo/369ai_fix/website/models/spin_win.py).
//   GET   -> {ok, win: {id, item_id, prize, code, valid_until, state, order} | null}  their current win
//   POST  -> {ok, win, again?}  a spin (`again`: they spun already in the window; the same win)
// Errors: 401 sign in; 'off' = the wheel is switched off in Odoo; 'paused' = nothing can be
// won right now; 'too many'; 503 unavailable.
import type { APIRoute } from 'astro';
import { me, secureOf } from '../../lib/account';
import { hostOf, ipOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

async function call(method: string, request: Request, cookies: any, socket?: string) {
  const host = hostOf(request);
  const who = await me(host, cookies, secureOf(request)).catch(() => null);
  if (!who?.partner_id) return json({ ok: false, error: 'sign in' }, 401);
  try {
    const r = await odooCall<{ ok: boolean; error?: string }>(host, 'fix.spin.win', method, {
      payload: { host, partner_id: who.partner_id, phone: who.phone || '', ip: ipOf(request, socket) },
    });
    return json(r, r.ok ? 200 : 422);
  } catch (e) {
    console.error('[spin] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
}

export const GET: APIRoute = ({ request, cookies }) => call('website_current', request, cookies);

export const POST: APIRoute = async ({ request, cookies, clientAddress }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  return call('website_spin', request, cookies, clientAddress);
};
