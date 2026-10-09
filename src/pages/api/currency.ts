// GET /api/currency — which currency should this visitor see?
// Runs on the server (not pre-rendered). Returns only what the page needs to display
// prices; no API keys or raw provider data ever leave the server.
import type { APIRoute } from 'astro';
import { resolveDisplayCurrency } from '../../lib/currency';
import { clientIp, countryFromIp, countryOfThisMachine, isPublicIp } from '../../lib/currency/geo';
import { getSettings } from '../../lib/settings';

export const prerender = false;

const ALLOW_TEST = process.env.ALLOW_TEST_GEO === '1' || import.meta.env.DEV;

export const GET: APIRoute = async ({ request, clientAddress }) => {
  const { autoCurrency } = await getSettings();
  const url = new URL(request.url);

  // Test override (?country=IN or X-Test-Country: IN) — only in development / when ALLOW_TEST_GEO=1
  const raw = request.headers.get('x-test-country') || url.searchParams.get('country');
  const override = ALLOW_TEST && raw && /^[A-Za-z]{2}$/.test(raw) ? raw.toUpperCase() : null;

  const ip = clientIp(request, clientAddress);
  // On a developer's own computer the visitor is 127.0.0.1 — use the machine's public IP instead
  const devCountry = !override && import.meta.env.DEV && !isPublicIp(ip) ? await countryOfThisMachine() : null;

  let result;
  try {
    result = await resolveDisplayCurrency(ip, autoCurrency, override ?? devCountry);
  } catch {
    result = null; // never fail the page: fall through to base currency
  }

  const body = result ?? (await resolveDisplayCurrency('', false));
  // Visitor's country is reported even when conversion is off (used e.g. for the phone country code)
  const visitor = result?.country ?? override ?? devCountry ?? (await countryFromIp(ip).catch(() => null));
  return new Response(
    JSON.stringify({
      enabled: body.enabled,
      base: body.base,
      currency: body.currency,
      rate: Number(body.rate.toFixed(6)),
      country: body.country,
      visitor,
      reason: body.reason,
      format: body.format,
    }),
    {
      headers: {
        'content-type': 'application/json; charset=utf-8',
        // always fresh: an admin change must show on the next page load (server caches keep this fast)
        'cache-control': 'no-store',
        vary: 'x-test-country',
      },
    },
  );
};
