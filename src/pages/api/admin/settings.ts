// POST /api/admin/settings — admin turns Automatic Currency Conversion on/off.
// Accepts a normal form post (from /admin) or JSON { autoCurrency: boolean }.
import type { APIRoute } from 'astro';
import { isAdmin, sameOrigin } from '../../../lib/adminAuth';
import { getSettings, saveSettings } from '../../../lib/settings';

export const prerender = false;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });

export const GET: APIRoute = async ({ cookies }) => {
  if (!isAdmin(cookies)) return json({ error: 'unauthorised' }, 401);
  return json(await getSettings());
};

export const POST: APIRoute = async ({ request, cookies, redirect }) => {
  if (!sameOrigin(request)) return json({ error: 'bad origin' }, 403);
  if (!isAdmin(cookies)) return json({ error: 'unauthorised' }, 401);

  const isForm = (request.headers.get('content-type') || '').includes('form');
  let value: unknown;
  if (isForm) {
    const f = await request.formData();
    value = f.get('autoCurrency') === 'on' ? true : f.get('autoCurrency') === 'off' ? false : undefined;
  } else {
    value = (await request.json().catch(() => ({})))?.autoCurrency;
  }
  if (typeof value !== 'boolean') return json({ error: 'autoCurrency must be true or false' }, 400);

  const saved = await saveSettings({ autoCurrency: value });
  return isForm ? redirect('/admin?saved=1', 303) : json(saved);
};
