// Pictures chosen in Odoo's "Fix Website" app (module 369ai_fix_website_content), served from
// this site so the browser never talks to Odoo: /web/image/fix.web.image/9/image_512?unique=…
// and /web/image/device.brand/57/web_logo?unique=…  Only those two kinds of picture pass; any
// other Odoo image path is refused. Odoo's caching headers are passed through, so the
// `unique=` URLs (they change whenever a picture is replaced) can be cached by the browser.
import type { APIRoute } from 'astro';
import { dbFor, hostOf, odooUrl } from '../../../lib/odoo';

export const prerender = false;

const ALLOWED = [
  /^fix\.web\.image\/\d+\/image_(1920|1024|512|256|128)$/,
  /^device\.brand\/\d+\/web_logo$/,
];
const PASS = ['content-type', 'content-length', 'cache-control', 'etag', 'last-modified', 'expires'];

export const GET: APIRoute = async ({ params, request, url }) => {
  const path = params.path || '';
  if (!ALLOWED.some((re) => re.test(path))) return new Response('Not found', { status: 404 });
  const db = dbFor(hostOf(request));
  if (!db) return new Response('Not found', { status: 404 });

  const headers: Record<string, string> = { 'x-odoo-database': db };
  const inm = request.headers.get('if-none-match');
  if (inm) headers['if-none-match'] = inm;
  const unique = url.searchParams.get('unique');

  let r: Response;
  try {
    r = await fetch(`${odooUrl()}/web/image/${path}${unique ? `?unique=${encodeURIComponent(unique)}` : ''}`, {
      headers,
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    return new Response('Picture not available', { status: 502, headers: { 'cache-control': 'no-store' } });
  }
  const out = new Headers();
  for (const k of PASS) {
    const v = r.headers.get(k);
    if (v) out.set(k, v);
  }
  if (!out.has('cache-control')) out.set('cache-control', unique ? 'public, max-age=604800' : 'public, max-age=300');
  return new Response(r.status === 304 ? null : r.body, { status: r.status, headers: out });
};
