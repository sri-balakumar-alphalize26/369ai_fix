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
| `ODOO_URL` | for Odoo | Odoo server, e.g. `http://127.0.0.1:8069` |
| `ODOO_DB` | for Odoo | Default Odoo database when no route matches |
| `ODOO_ROUTES` | for Odoo | Which database each host feeds: `danatfix.com,www.danatfix.com=DUBAI_TEST;other.com=OTHER_DB` |
| `ODOO_API_KEY` | for Odoo | API key of the Odoo bot user; per database: `ODOO_KEY_<DB>` (e.g. `ODOO_KEY_OTHER_DB`) |

## Online Service: bookings into Odoo, alarm, WhatsApp status, "My Orders"

Odoo module: `odoo/369ai_fix_customer_module` (Odoo 19, depends on `mobile_repair`).
It adds **IT & Mobile Repair ▸ Online Service**: Doorstep Service / Pickup & Service /
All Orders, *Create Job Card*, an alarm on every Odoo page for new orders, a WhatsApp
message to the customer at every status (order + job card; through the
`whatsapp_gateway` module when installed, skipped otherwise), WhatsApp login codes,
and **Configuration ▸ Websites** (which host may send to this database) and
**Status Messages** (editable texts).

Website side (all server-side, nothing secret reaches the browser):

- `src/lib/odoo.ts` — picks the database by the request's `Host` header (`ODOO_ROUTES`),
  calls Odoo `POST /json/2/<model>/<method>` with the bot key + `X-Odoo-Database`,
  signs the customer cookie. Note: behind the Cloudflare tunnel `request.url` is
  localhost, so host/origin checks read the `Host` header.
- `/api/booking` — the services wizard (`src/pages/services.astro`, step 4) sends the
  booking here alongside the WhatsApp message; Odoo failures never block the customer.
  The carts do not collect name/phone, so they stay WhatsApp-only.
- `/api/otp/request`, `/api/otp/verify`, `/api/my-orders` + page `/track` ("My Orders"):
  mobile number → 6-digit code on WhatsApp → orders with live status, refreshed every 15 s.

Odoo methods the site calls (bot user, `online.service.order` / `online.service.otp`):
`website_create(payload)`, `customer_orders(host, phone)`, `otp_request(host, phone, ip)`,
`otp_verify(host, phone, code)`. A host that is not an active record in
Configuration ▸ Websites is refused.

**Connect another website / database:** install the module in that database, add the
website under Online Service ▸ Configuration ▸ Websites, create an internal user with the
*Mobile Repair / Receptionist* group and an API key, then add the host to `ODOO_ROUTES`
and the key as `ODOO_KEY_<DB>` in the website's `.env`.

**Deploy the Odoo module:** the server runs it from `/opt/odoo/369ai_fix_addons/`
(in `addons_path`). After changing it, copy the folder there and upgrade only the
databases that have it: `odoo-bin -c /etc/odoo19.conf -d DUBAI_TEST -u 369ai_fix_customer_module --stop-after-init --no-http`.
The website itself redeploys from GitHub `main` automatically (`danatfix-deploy.timer`).

## Repair catalogue: repairs as products in Odoo

Odoo module: `odoo/369ai_fix_repair_module` (Odoo 19, depends on `mobile_repair`; it only
extends it). Repairs are IT & Mobile Repair's own **Products ▸ Services**, priced on the product.
The module adds three things:

- **Device categories on products.** Together with the product's Brand / Series / Model
  (already in mobile_repair), a service is either general ("Screen replacement", Mobile Phone,
  15.000) or for one device ("Screen replacement - iPhone 13", Apple / iPhone 13, 45.000).
  The Services list shows categories, brand and model.
- **Job card ▸ Required Services** only offers the services whose categories, brand, series
  and model match the card or are empty. The price comes from the product, as before. Spare
  parts keep their own price. Give repair services a *price-included* 5% VAT so the price is
  what the customer pays.
- **Settings ▸ Inspection ▸ Visit fee + quote:**
  - New job cards start as *Paid Inspection*. The fee is mobile_repair's *Inspection Charge
    Product*.
  - On *Create Quotation*, a card with a repair has the fee waived.
  - A card with only the visit-fee line (the customer declined) bills that line alone.
    Either way the fee is never charged twice.
- **Install only:** adds the CCTV Installation, Networking & Wi-Fi, Data Recovery and IT Support
  categories (with their brands and models), the website's 65 repairs as services at price 0,
  and an *Inspection / Visit Fee* product if none is set. Existing records are never changed.
  The data is `data/seed_repairs.json`, built from `src/data/` by
  `node scripts/export-repair-seed.mjs`.

**Local Odoo:** the folder is linked into the server's addons folder (a junction, as for
369Mart). Restart the `odoo-server-19.0` service after adding a new module.

**Deploy:** copy the folder to `/opt/odoo/369ai_fix_addons/`, then install with
`odoo-bin -c /etc/odoo19.conf -d DUBAI_TEST -i 369ai_fix_repair_module --stop-after-init --no-http`.
Use `-u` instead of `-i` for later updates.

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
