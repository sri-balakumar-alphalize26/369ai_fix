// POST /api/booking-media - the customer's photos (max 5) and video (max 1) for a booking,
// sent right after /api/booking with the upload token it returned. multipart/form-data:
// ref, token, files[]. Odoo re-checks the token, the counts, the sizes and that each file
// really is a picture or a video, then attaches them to the job card.
import type { APIRoute } from 'astro';
import { hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const PHOTO_BYTES = 5 * 1024 * 1024;
const VIDEO_BYTES = 30 * 1024 * 1024;

export const POST: APIRoute = async ({ request }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const form = await request.formData().catch(() => null);
  if (!form) return json({ ok: false, error: 'bad request' }, 400);
  const ref = String(form.get('ref') || '').slice(0, 30);
  const token = String(form.get('token') || '').slice(0, 100);
  const files = form.getAll('files').filter((f): f is File => f instanceof File).slice(0, 6);
  if (!ref || !token || !files.length) return json({ ok: false, error: 'nothing to send' }, 400);
  const out = [];
  for (const f of files) {
    const video = f.type.startsWith('video/');
    if (f.size > (video ? VIDEO_BYTES : PHOTO_BYTES)) return json({ ok: false, error: `${f.name} is too large` }, 413);
    out.push({ name: f.name.slice(0, 80), data: Buffer.from(await f.arrayBuffer()).toString('base64') });
  }
  const host = hostOf(request);
  try {
    const r = await odooCall<{ ok: boolean; error?: string }>(host, 'online.service.order', 'website_attach',
      { host, ref, token, files: out });
    return json(r, r.ok ? 200 : 422);
  } catch (e) {
    console.error('[booking-media] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
