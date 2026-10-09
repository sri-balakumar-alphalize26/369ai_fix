// POST /api/otp/verify { phone, code } — on success the browser gets a signed, http-only
// cookie (30 days) that lets /api/my-orders show this number's orders on this site.
import type { APIRoute } from 'astro';
import { sameOrigin } from '../../../lib/adminAuth';
import { digits, hostOf, json, odooCall, setCustomer } from '../../../lib/odoo';

export const prerender = false;

export const POST: APIRoute = async ({ request, cookies, url }) => {
  if (!sameOrigin(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  const phone = digits(b?.phone), code = digits(b?.code).slice(0, 6);
  if (phone.length < 7 || code.length !== 6) return json({ ok: false, error: 'Enter the 6-digit code.' }, 400);
  const host = hostOf(request);
  try {
    const r = await odooCall<{ ok: boolean; error?: string; left?: number }>(host, 'online.service.otp', 'otp_verify', { host, phone, code });
    if (!r.ok) {
      const msg = r.error === 'locked' ? 'Too many wrong tries. Ask for a new code.'
        : r.error === 'expired' ? 'This code has expired. Ask for a new one.'
        : `Wrong code.${r.left ? ` ${r.left} ${r.left === 1 ? 'try' : 'tries'} left.` : ''}`;
      return json({ ok: false, error: msg }, 401);
    }
    setCustomer(cookies, phone, host, url.protocol === 'https:' || request.headers.get('x-forwarded-proto') === 'https');
    return json({ ok: true });
  } catch (e) {
    console.error('[otp] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'Order tracking is not available right now.' }, 503);
  }
};
