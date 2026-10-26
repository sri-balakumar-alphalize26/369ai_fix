// GET /api/coupon?code=SPIN-DIAG-7K3Q - is this a Spin & Win prize code, and can it be used?
// {ok, known, valid?, prize?, valid_until?, reason?, win_id?}. `known` false for any other code
// (the shop's own offer codes go with the booking as plain text, as before). Signed in, the
// check also says when the code belongs to another customer.
import type { APIRoute } from 'astro';
import { me, secureOf } from '../../lib/account';
import { hostOf, json, odooCall } from '../../lib/odoo';

export const prerender = false;

export const GET: APIRoute = async ({ request, cookies }) => {
  const code = (new URL(request.url).searchParams.get('code') || '').trim().toUpperCase().slice(0, 30);
  if (!code) return json({ ok: false, error: 'no code' }, 400);
  const host = hostOf(request);
  const who = await me(host, cookies, secureOf(request)).catch(() => null);
  try {
    const r = await odooCall<{ ok: boolean }>(host, 'fix.spin.win', 'website_coupon', {
      payload: { host, code, partner_id: who?.partner_id || 0 },
    });
    return json(r, r.ok ? 200 : 422);
  } catch (e) {
    console.error('[coupon] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
