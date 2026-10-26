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
//   POST address-update          {id, ...the same fields}  -> {address} (an address an order used gets a new id)
//   POST address-remove          {id}
//   POST address-default         {id}                     -> the list, as GET addresses
//   POST profile                 {name, email}            -> the profile, as GET me
import type { APIRoute } from 'astro';
import { clearSession, martAs, martFetch, me, secureOf, sessionOf, setSession } from '../../../lib/account';
import { clearCustomer, hostOf, ipOf, json, originOk, setCustomer } from '../../../lib/odoo';

export const prerender = false;

const pass = (r: { status: number; data: any }) => json(r.data, r.status >= 500 && r.status !== 503 ? 502 : r.status);
// An address is in Oman (3-digit postal code) or India (6-digit pincode), as on 369 Mart.
const countryOf = (v: unknown) => (String(v || '').toUpperCase() === 'IN' ? 'IN' : 'OM');
const ADDRESS_KEYS = ['label', 'name', 'phone', 'alt', 'line', 'area', 'town', 'pin', 'landmark', 'lat', 'lng', 'state_id'];
function addressOf(body: any): Record<string, unknown> {
  const b: Record<string, unknown> = { country_id: countryOf(body.country_id) };
  for (const k of ADDRESS_KEYS) if (body[k] !== undefined && body[k] !== null && body[k] !== '') b[k] = typeof body[k] === 'number' ? body[k] : String(body[k]).slice(0, 200);
  return b;
}
const idOf = (v: unknown) => { const n = Number(v); return Number.isInteger(n) && n > 0 ? n : 0; };

export const GET: APIRoute = async ({ params, request, cookies }) => {
  const host = hostOf(request);
  const secure = secureOf(request);
  switch (params.action) {
    case 'phone-form': {
      const country = new URL(request.url).searchParams.get('country') || '';
      return pass(await martFetch(host, `/369mart/auth/phone-form${country ? `?country=${encodeURIComponent(country)}` : ''}`));
    }
    case 'me': {
      const who = await me(host, cookies, secure);
      return who ? json(who) : json({ ok: false }, 401);
    }
    case 'addresses':
      return pass(await martAs(host, '/369mart/addresses', cookies, secure));
    case 'pincode': {
      // postal code -> wilayat, governorate and area, from 369 Mart's lookup in Odoo (as on 369 Mart)
      const pin = (new URL(request.url).searchParams.get('pin') || '').replace(/\D/g, '').slice(0, 10);
      if (!pin) return json({ ok: false }, 400);
      return pass(await martFetch(host, `/369mart/pincode/${pin}`));
    }
    case 'address-form': {
      // what the address form needs for Oman or India (e.g. the governorates / states, when Odoo has them)
      const country = countryOf(new URL(request.url).searchParams.get('country'));
      return pass(await martAs(host, `/369mart/addresses/form?country=${country}`, cookies, secure));
    }
  }
  return json({ ok: false, error: 'not found' }, 404);
};

export const POST: APIRoute = async ({ params, request, cookies, clientAddress }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const host = hostOf(request);
  const ip = ipOf(request, clientAddress);
  const body = await request.json().catch(() => ({}));
  const secure = secureOf(request);
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
      if (r.data?.ok && r.session) {
        setSession(cookies, r.session, secure);
        // one sign-in for the whole site: My orders knows this number too
        if (r.data.phone) setCustomer(cookies, String(r.data.phone).replace(/\D/g, ''), host, secure);
      }
      return res;
    }
    case 'logout': {
      const session = sessionOf(cookies);
      if (session) await martFetch(host, '/369mart/auth/logout', { method: 'POST', session });
      clearSession(cookies);
      clearCustomer(cookies);        // signed out everywhere, My orders too
      return json({ ok: true });
    }
    case 'addresses':
      return pass(await martAs(host, '/369mart/addresses', cookies, secure, { method: 'POST', body: addressOf(body) }));
    case 'address-update':
    case 'address-remove':
    case 'address-default': {
      const id = idOf(body.id);
      if (!id) return json({ ok: false, error: 'No such address.' }, 400);
      if (params.action === 'address-update') return pass(await martAs(host, `/369mart/addresses/${id}`, cookies, secure, { method: 'PATCH', body: addressOf(body) }));
      if (params.action === 'address-remove') return pass(await martAs(host, `/369mart/addresses/${id}`, cookies, secure, { method: 'DELETE' }));
      return pass(await martAs(host, `/369mart/addresses/${id}/default`, cookies, secure, { method: 'POST', body: {} }));
    }
    case 'profile': {
      // the mobile number is the account's identity: it changes only through a new WhatsApp code
      // an empty email is left out: 369 Mart refuses to blank one (it can be the login)
      const b: Record<string, string> = { name: String(body.name || '').trim().slice(0, 80) };
      const email = String(body.email || '').trim().slice(0, 120);
      if (email) b.email = email;
      return pass(await martAs(host, '/369mart/profile', cookies, secure, { method: 'PATCH', body: b }));
    }
  }
  return json({ ok: false, error: 'not found' }, 404);
};
