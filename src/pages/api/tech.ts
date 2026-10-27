// /api/tech - the technician's link from WhatsApp (v = visit, t = token), for the /tech page:
//   GET  ?v=&t=                                          what the page shows
//   POST {v, t, action: 'ping', lat, lng, accuracy, heading, speed, battery}   the phone's position
//   POST {v, t, action: 'on_the_way' | 'arrive' | 'start' | 'done', lat?, lng?, code?}   one step
//   POST {v, t, action: 'check_tick', item_id, done}                       a safety tick (after arriving)
//   POST {v, t, action: 'check_safety_photo' | 'check_side_photo' | 'check_video', photo_id?, data, name?}
//   POST {v, t, action: 'check_clear_safety'}                              take the safety photos again
//   POST {v, t, action: 'result_issue', issue_id, on, brand_id?}       tick / untick a problem found
//   POST {v, t, action: 'result_parts', query}  /  'result_add_part' {product_id, brand_id?}  /  'result_remove_part' {line_id}
//   POST {v, t, action: 'result_fixed' | 'result_quote' {plan, days, unit, part_days}, note?}
//   POST {v, t, action: 'result_approved_here' | 'result_declined_here' | 'result_later' | 'result_take' {accessory_ids, no_accessories}}
//   POST {v, t, action: 'result_outcome', outcome, note?, days?, unit?}   "Can it be fixed?"
//   POST {v, t, action: 'result_price', price, line_id? | product_id?}     the repair's (labour) price
//   POST {v, t, action: 'result_labour', price}                           Labour only: the charge (0 = free)
//   POST {v, t, action: 'result_request', name?, price?, data?}           a part not in the list: the office sources it (visit closes)
//   POST {v, t, action: 'result_ask', name, price?, data?}  /  'result_ask_cancel'   ask the office and wait at the door
//   POST {v, t, action: 'result_alts' | 'result_choose', line_id}          another grade of a part / keep this grade
//   POST {v, t, action: 'close_photo' {data} | 'close_clear' | 'close_pay' {method_id, amount?} | 'close_free' | 'close_code' {code}}   Finish
import type { APIRoute } from 'astro';
import { hostOf, json, odooCall, originOk } from '../../lib/odoo';

export const prerender = false;

const s = (v: unknown, n: number) => String(v ?? '').trim().slice(0, n);
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const ACTIONS = new Set(['ping', 'on_the_way', 'arrive', 'start', 'done',
  // before work: the safety check, the photos and the video (Odoo checks the files' content)
  'check_tick', 'check_safety_photo', 'check_side_photo', 'check_video', 'check_clear_safety',
  // while working: what was found, the parts, and the result
  'result_issue', 'result_parts', 'result_note', 'result_add_part', 'result_remove_part',
  'result_fixed', 'result_quote',
  // the customer's answer at the door, and taking the device to the office
  'result_approved_here', 'result_declined_here', 'result_later', 'result_take',
  // can it be fixed?, the labour price, a part not in the list, two grades of a part
  'result_outcome', 'result_price', 'result_request', 'result_alts', 'result_choose',
  // a part asked of the office while the technician waits (the office answers on the Booking Desk)
  'result_ask', 'result_ask_cancel',
  // Labour only: the labour charge (0 = free); any charge is quoted to the customer first
  'result_labour',
  // after the repair: the photo, the payment and the customer's finish code
  'close_photo', 'close_clear', 'close_pay', 'close_free', 'close_code']);
const MAX_B64 = 42 * 1024 * 1024;   // a 30 MB video, base64

export const GET: APIRoute = async ({ request }) => {
  const q = new URL(request.url).searchParams;
  const host = hostOf(request);
  try {
    return json(await odooCall(host, 'fix.service.visit', 'tech_page', { host, ref: s(q.get('v'), 30), token: s(q.get('t'), 100) }));
  } catch (e) {
    console.error('[tech] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};

export const POST: APIRoute = async ({ request }) => {
  if (!originOk(request)) return json({ ok: false, error: 'bad origin' }, 403);
  const b = await request.json().catch(() => ({}));
  const action = s(b.action, 20);
  if (!ACTIONS.has(action)) return json({ ok: false, error: 'unknown action' }, 400);
  const host = hostOf(request);
  const data = typeof b.data === 'string' ? b.data : '';
  if (data.length > MAX_B64) return json({ ok: false, error: 'check', message: 'The file is too large.' }, 413);
  const check = action.startsWith('check_') ? {
    item_id: num(b.item_id), photo_id: num(b.photo_id), done: !!b.done, name: s(b.name, 80), data,
  } : action.startsWith('result_') ? {
    query: s(b.query, 80), product_id: num(b.product_id), brand_id: num(b.brand_id), line_id: num(b.line_id),
    issue_id: num(b.issue_id), on: !!b.on, plan: s(b.plan, 20),
    qty: num(b.qty), days: num(b.days), part_days: num(b.part_days), unit: b.unit === 'weeks' ? 'weeks' : 'days',
    take: !!b.take, no_accessories: !!b.no_accessories,
    note: b.note === undefined ? null : s(b.note, 2000),
    accessory_ids: Array.isArray(b.accessory_ids) ? b.accessory_ids.filter((x: unknown) => Number.isInteger(x)).slice(0, 50) : [],
    outcome: s(b.outcome, 20), price: num(b.price), name: s(b.name, 120), data,
  } : action.startsWith('close_') ? {
    data, method_id: num(b.method_id), amount: num(b.amount),
  } : {};
  try {
    return json(await odooCall(host, 'fix.service.visit', 'tech_page', {
      host, ref: s(b.v, 30), token: s(b.t, 100), action, code: s(b.code, 8),
      lat: num(b.lat), lng: num(b.lng), accuracy: num(b.accuracy),
      heading: num(b.heading), speed: num(b.speed), battery: num(b.battery), ...check,
    }, data ? 60000 : 8000));
  } catch (e) {
    console.error('[tech] Odoo:', (e as Error).message);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
};
