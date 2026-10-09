# Danat Fix / 369 ai Fix — doorstep repair website

Astro 5 site. Pages are pre-rendered (static); a small Node server (`@astrojs/node`)
runs the currency API and the admin.

## Run

```bash
npm install
npm run dev          # development: http://localhost:4400 (or the port Astro prints)
npm run build        # production build → dist/
node dist/server/entry.mjs   # production server (PORT and HOST env vars, default 4321)
```

Hosting must run Node (VPS, Render, Railway, …). For Netlify/Vercel swap the adapter
in `astro.config.mjs`.

## Environment variables (`.env`, never committed)

| Variable | Required | Purpose |
|---|---|---|
| `ADMIN_SECRET` | recommended | Signs the admin login cookie (random long string) |
| `FX_API_KEY` | no | Use the keyed exchangerate-api.com v6 instead of the free open.er-api.com |
| `ALLOW_TEST_GEO` | no | `1` lets `?country=XX` / `X-Test-Country` simulate a country on a production server (testing only) |
| `FX_API_URL` | no | Override the rate provider URL (`{BASE}` placeholder) — used by tests |

## Automatic currency conversion

Visitors see prices in their own country's currency; stored prices never change.

- **Base amounts**: `src/data/site.ts` (`site.currency` = `OMR`, `PRICE`, `price()`).
- **Service** (`src/lib/currency/`):
  - `countryCurrency.ts` — every country → its ISO-4217 currency, plus validation.
  - `geo.ts` — visitor IP (`X-Forwarded-For`/socket) → country via api.country.is,
    fallbacks ipwho.is and ipapi.co. Cached per IP 24 h (failures 10 min), max 10k IPs,
    simultaneous lookups for one IP shared.
  - `rates.ts` — live rates from open.er-api.com, validated, cached in memory and
    `.cache/rates-<BASE>.json` for 6 h; one shared request when many visitors arrive
    at once; on provider failure the last good rates are used.
  - `format.ts` — `Intl.NumberFormat` (₹1,000 · $12.00 · AED 44.00 · OMR 4.60).
  - `index.ts` — `resolveDisplayCurrency()` combines the above with the admin setting.
- **API**: `GET /api/currency` → `{ enabled, base, currency, rate, country, reason, format }`.
  `Cache-Control: no-store`; the server-side caches make each call ~2 ms.
- **Browser**: `src/components/LocalCurrency.astro` calls the API once per page load and
  rewrites displayed "OMR n" amounts. No rates, keys or third-party calls in the browser.
  WhatsApp booking messages keep the base currency.
- **Fallback**: setting off, unknown IP/country, unsupported currency, missing rate or
  any error → base currency (OMR), exactly as before.

### Admin

Two ways in, same login (ID **Alphalize**, password **DanatFix1** — set in code in `src/lib/adminAuth.ts`; change them there):

- **Quick pop-up:** open the Home page with `?admin=danatfix1` (e.g. `http://danat.alphalize.com/?admin=danatfix1`; key checked on the server, any letter case — other values do nothing). A pop-up with the logo asks for the ID and password, then shows the **Location-based currency** ON/OFF switch.
- **Full dashboard:** `/admin` → **Automatic Currency Conversion: Enable / Disable**, live status and preview.

The check runs on the server only; 5 wrong tries lock that IP for 15 minutes.
Stored in `data/settings.json` (`src/lib/settings.ts`). Login cookie is signed, http-only,
SameSite=Strict, 8 h; 5 wrong passwords lock that IP for 15 min; cross-site posts rejected.

### Testing a country locally

`http://localhost:4400/?country=AE` (dev only) or
`curl -H "X-Test-Country: AE" http://localhost:4400/api/currency`.

## Backup

Test-mode backup before this feature: branch `backup/test-mode-2026-10-01`,
tag `backup-test-mode-2026-10-01`.
