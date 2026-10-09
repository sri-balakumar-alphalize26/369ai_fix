// POST /api/otp/request { phone } — Odoo sends a 6-digit login code on WhatsApp.
// The answer is the same whether or not the number has orders (no "who booked" leak).
import type { APIRoute } from 'astro';
import { digits, hostOf, ipOf, json, odooCall, originOk } from '../../../lib/odoo';

export const prerender = false;

export const POST: APIRoute = async ({ request, clientAddress }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  const phone = digits(b?.phone);
  if (phone.length < 7) return json({ ok: false, error: 'Please enter your full mobile number with country code.' }, 400);
  const host = hostOf(request);
  try {
    const r = await odooCall<{ ok: boolean; error?: string }>(host, 'online.service.otp', 'otp_request',
      { host, phone, ip: ipOf(request, clientAddress) });
    if (r.error === 'too many') return json({ ok: false, error: 'Too many codes asked. Please wait 15 minutes.' }, 429);
    if (r.error === 'whatsapp') return json({ ok: false, error: 'We could not send the WhatsApp code right now. Please try again in a minute.' }, 503);
    if (!r.ok) return json({ ok: false, error: 'Please check the number.' }, 400);
    return json({ ok: true });
  } catch (e) {
    console.error('[otp] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'Order tracking is not available right now.' }, 503);
  }
};
