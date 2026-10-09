// POST /api/admin/login — sign-in for the ?admin= pop-up on Home. JSON { id, password }.
// GET ?key=… tells the pop-up whether the link key is right (only then it opens) and whether
// this browser is already signed in. DELETE signs out.
// Same checks as /admin: server-side compare, 5 wrong tries → 15 min lock, http-only cookie.
import type { APIRoute } from 'astro';
import { isAdmin, login, logout, sameOrigin, gateOk } from '../../../lib/adminAuth';

export const prerender = false;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });

export const GET: APIRoute = async ({ cookies, url }) => {
  if (!gateOk(url.searchParams.get('key'))) return json({ gate: false });
  return json({ gate: true, admin: isAdmin(cookies) });
};

export const POST: APIRoute = async ({ request, cookies, clientAddress, url }) => {
  if (!sameOrigin(request)) return json({ error: 'bad origin' }, 403);
  const body = await request.json().catch(() => ({}));
  const id = typeof body?.id === 'string' ? body.id.slice(0, 100) : '';
  const password = typeof body?.password === 'string' ? body.password.slice(0, 200) : '';
  const r = login(id, password, clientAddress, cookies, url.protocol === 'https:');
  if (r === 'ok') return json({ ok: true });
  return json({ ok: false, error: r === 'locked' ? 'Too many wrong attempts. Try again in 15 minutes.' : 'Wrong ID or password.' }, r === 'locked' ? 429 : 401);
};

export const DELETE: APIRoute = async ({ request, cookies }) => {
  if (!sameOrigin(request)) return json({ error: 'bad origin' }, 403);
  logout(cookies);
  return json({ ok: true });
};
