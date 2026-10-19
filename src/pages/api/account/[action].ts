// /api/account/<action> - the customer's sign-in and address book, passed to 369 Mart's
// account routes in Odoo (see src/lib/account.ts):
//   GET  phone-form?country=om   country picker data
//   POST phone-start             {phone, country, purpose: signin|signup, name?}  -> WhatsApp code
//   POST phone-verify            {phone, country, code, purpose, name?, email?}   -> signed in (cookie)
//   GET  me                      who is signed in
//   POST logout
//   GET  addresses               saved addresses
//   GET  pincode?pin=133         city (wilayat), governorate and areas for a postal code (Oman 3 digits, India 6)
//   GET  address-form?country=OM what the form needs for OM or IN (states)
//   POST addresses               a new address {label, name, phone, alt, line, area, town, pin, landmark, lat, lng, country_id}
import type { APIRoute } from 'astro';
import { clearSession, martFetch, me, sessionOf, setSession } from '../../../lib/account';
import { hostOf, ipOf, json, originOk } from '../../../lib/odoo';

export const prerender = false;

const pass = (r: { status: number; data: any }) => json(r.data, r.status >= 500 && r.status !== 503 ? 502 : r.status);
// An address is in Oman (3-digit postal code) or India (6-digit pincode), as on 369 Mart.
const countryOf = (v: unknown) => (String(v || '').toUpperCase() === 'IN' ? 'IN' : 'OM');

export const GET: APIRoute = async ({ params, request, cookies }) => {
  const host = hostOf(request);
  switch (params.action) {
    case 'phone-form': {
      const country = new URL(request.url).searchParams.get('country') || '';
      return pass(await martFetch(host, `/369mart/auth/phone-form${country ? `?country=${encodeURIComponent(country)}` : ''}`));
    }
    case 'me': {
      const who = await me(host, cookies);
      return who ? json(who) : json({ ok: false }, 401);
    }
    case 'addresses': {
      const session = sessionOf(cookies);
      if (!session) return json({ ok: false, error: 'Please sign in.' }, 401);
      const r = await martFetch(host, '/369mart/addresses', { session });
      if (r.status === 401) clearSession(cookies);
      return pass(r);
    }
    case 'pincode': {
      // postal code -> wilayat, governorate and area, from 369 Mart's lookup in Odoo (as on 369 Mart)
      const pin = (new URL(request.url).searchParams.get('pin') || '').replace(/\D/g, '').slice(0, 10);
      if (!pin) return json({ ok: false }, 400);
      return pass(await martFetch(host, `/369mart/pincode/${pin}`));
    }
    case 'address-form': {
      // what the address form needs for Oman or India (e.g. the governorates / states, when Odoo has them)
      const session = sessionOf(cookies);
      if (!session) return json({ ok: false, error: 'Please sign in.' }, 401);
      const country = countryOf(new URL(request.url).searchParams.get('country'));
      return pass(await martFetch(host, `/369mart/addresses/form?country=${country}`, { session }));
    }
  }
  return json({ ok: false, error: 'not found' }, 404);
};

export const POST: APIRoute = async ({ params, request, cookies, clientAddress }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const host = hostOf(request);
  const ip = ipOf(request, clientAddress);
  const body = await request.json().catch(() => ({}));
  const secure = new URL(request.url).protocol === 'https:' || request.headers.get('x-forwarded-proto') === 'https';
  switch (params.action) {
    case 'phone-start': {
      const b = { phone: String(body.phone || '').slice(0, 30), country: String(body.country || '').slice(0, 4),
                  purpose: body.purpose === 'signup' ? 'signup' : 'signin', name: String(body.name || '').slice(0, 80) };
      return pass(await martFetch(host, '/369mart/auth/phone/start', { method: 'POST', body: b, ip }));
    }
    case 'phone-verify': {
      const b = { phone: String(body.phone || '').slice(0, 30), country: String(body.country || '').slice(0, 4),
                  code: String(body.code || '').replace(/\D/g, '').slice(0, 6),
                  purpose: body.purpose === 'signup' ? 'signup' : 'signin',
                  name: String(body.name || '').slice(0, 80), email: String(body.email || '').slice(0, 120),
                  password: body.password ? String(body.password).slice(0, 128) : undefined };
      const r = await martFetch(host, '/369mart/auth/phone/verify', { method: 'POST', body: b, fresh: true, ip });
      const res = pass(r);
      if (r.data?.ok && r.session) setSession(cookies, r.session, secure);
      return res;
    }
    case 'logout': {
      const session = sessionOf(cookies);
      if (session) await martFetch(host, '/369mart/auth/logout', { method: 'POST', session });
      clearSession(cookies);
      return json({ ok: true });
    }
    case 'addresses': {
      const session = sessionOf(cookies);
      if (!session) return json({ ok: false, error: 'Please sign in.' }, 401);
      const keys = ['label', 'name', 'phone', 'alt', 'line', 'area', 'town', 'pin', 'landmark', 'lat', 'lng', 'state_id'];
      const b: Record<string, unknown> = { country_id: countryOf(body.country_id) };
      for (const k of keys) if (body[k] !== undefined && body[k] !== null && body[k] !== '') b[k] = typeof body[k] === 'number' ? body[k] : String(body[k]).slice(0, 200);
      const r = await martFetch(host, '/369mart/addresses', { method: 'POST', body: b, session });
      if (r.status === 401) clearSession(cookies);
      return pass(r);
    }
  }
  return json({ ok: false, error: 'not found' }, 404);
};
