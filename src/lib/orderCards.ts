// The customer's order cards (My orders on /track and /account): what /api/my-orders returns,
// drawn as HTML. Browser-side; the styles are in components/OrderCards.astro.

export const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

// Every time and date on the order pages in Oman time (the business's own clock), whatever the
// customer's browser is set to: the same as the times Odoo writes (e.g. "13:00-16:00").
const TZ = 'Asia/Muscat';
const hm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: TZ });

// The technician's visit (doorstep orders): who, live position, ETA and the arrival code.
function visitBlock(v: any) {
  if (!v || v.state === 'cancelled') return '';
  const tech = v.technician;
  const live = v.live;
  const slot = v.slot ? new Date(v.slot.start).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: TZ }) : '';
  const facts = [
    v.eta_minutes ? `<b>About ${esc(String(v.eta_minutes))} min away</b>${v.eta_at ? ` · by ${esc(hm(v.eta_at))}` : ''}` : '',
    v.distance_km ? `${esc(Number(v.distance_km).toFixed(1))} km from you` : '',
    live ? (live.stale ? 'Signal lost, showing the last known place' : `Updated ${esc(hm(live.fix_on))}`) : '',
  ].filter(Boolean);
  return `
    <div class="tk-visit">
      <div class="tk-vhead">
        ${tech?.photo ? `<img src="${esc(tech.photo)}" alt="" width="44" height="44" onerror="this.outerHTML='&lt;span class=&quot;tk-vav&quot; aria-hidden=&quot;true&quot;&gt;&lt;/span&gt;'" />` : '<span class="tk-vav" aria-hidden="true"></span>'}
        <div>
          <b>${esc(v.state_label)}</b>
          <span>${tech ? esc(tech.name) : 'We are choosing your technician'}${slot ? ` · ${esc(slot)}` : ''}</span>
        </div>
        ${tech?.phone ? `<a class="tk-vcall" href="tel:+${esc(String(tech.phone).replace(/\D/g, ''))}">Call</a>` : ''}
      </div>
      ${facts.length ? `<p class="tk-vfacts">${facts.join(' · ')}</p>` : ''}
      ${live ? `<a class="tk-vmap" href="https://www.google.com/maps/search/?api=1&query=${live.lat},${live.lng}" target="_blank" rel="noopener">See the technician on the map →</a>` : ''}
      ${v.arrival_code ? `<p class="tk-vcode">Arrival code <b>${esc(String(v.arrival_code))}</b><small>Give this code to the technician when they reach your door. Don't share it before.</small></p>` : ''}
      ${v.safety ? `<div class="tk-safe">
        ${v.safety.photo ? `<img src="${esc(v.safety.photo)}" alt="Your technician, ready for work" width="64" height="64" />` : ''}
        <div><b>Safety check done ✅</b><span>${(v.safety.items || []).map((x: string) => esc(x)).join(' · ')}</span>
        ${v.safety.at ? `<small>Before starting, at ${esc(hm(v.safety.at))}</small>` : ''}</div></div>` : ''}
      ${closeBlock(v.close)}
      ${track(v.steps, ' tk-vtrack')}
    </div>`;
}

// After the repair: the finish code while the technician finishes, then the receipt (paid,
// warranty) and the rating.
function closeBlock(c: any) {
  if (!c) return '';
  if (c.finishing) {
    return c.finish_code ? `<p class="tk-vcode">Finish code <b>${esc(String(c.finish_code))}</b><small>Your repair is done. Check your device, then give this code to the technician.</small></p>` : '';
  }
  const facts = [
    c.paid ? `<span><b>Paid</b>${esc(c.paid)}</span>` : '',
    c.warranty_until ? `<span><b>Warranty</b>until ${esc(day(c.warranty_until))}</span>` : '',
    c.rating ? `<span><b>Your rating</b>${'★'.repeat(Math.max(0, Math.min(5, Number(c.rating))))}</span>` : '',
  ].filter(Boolean);
  return `<div class="tk-close">${facts.join('')}${c.rate_url ? `<a class="tk-vcall" href="${esc(c.rate_url)}">Rate your visit</a>` : ''}</div>`;
}

// what is happening now, in a line under the tracker (as on a shop's order page)
const NOW: Record<string, string> = {
  received: "We've got your booking and will confirm it shortly.",
  confirmed: 'Your booking is confirmed. We are arranging the technician visit.',
  inspection: 'Our technician is checking your device.',
  quotation: 'We sent you the price. Please approve or decline it.',
  repair: 'Your device is being repaired.',
  completed: 'Repair completed. Thank you for choosing us!',
};
// a simple picture of the device, from its type
const ICONS: [RegExp, string][] = [
  [/tablet|ipad/i, '<rect x="5" y="2.5" width="14" height="19" rx="2"/><path d="M11 18.5h2"/>'],
  [/phone|mobile|iphone/i, '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>'],
  [/laptop|macbook|notebook/i, '<rect x="4" y="4.5" width="16" height="11" rx="1.5"/><path d="M2 19.5h20"/>'],
  [/desktop|monitor|all-in-one|computer/i, '<rect x="3" y="3.5" width="18" height="13" rx="1.5"/><path d="M9 20.5h6M12 16.5v4"/>'],
  [/print/i, '<path d="M7 8.5v-5h10v5"/><rect x="3" y="8.5" width="18" height="8" rx="1.5"/><path d="M7 14.5h10v6H7z"/>'],
  [/watch/i, '<rect x="7" y="6.5" width="10" height="11" rx="2.5"/><path d="M9 6.5l1-4h4l1 4M9 17.5l1 4h4l1-4"/>'],
];
const WRENCH = '<path d="M14.5 6.5a4 4 0 0 0 5 5l-8.5 8.5a2.1 2.1 0 0 1-3-3l8.5-8.5a4 4 0 0 0-2-2z"/>';
const icon = (text: string) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS.find(([re]) => re.test(text))?.[1] ?? WRENCH}</svg>`;
const when = (s: string) => new Date(s.replace(' ', 'T') + 'Z').toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: TZ });
// a date (no time): read at midday so it is the same day in Oman for every browser
const day = (s: string) => new Date(s + 'T12:00:00Z').toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ });

function track(steps: any[], cls = '') {
  return `<ol class="tk-track${cls}">${steps.map((s: any) => `<li class="${s.done ? 'done' : ''}${s.current ? ' cur' : ''}">
    <i aria-hidden="true"></i><span>${esc(s.label)}${s.at && s.done ? `<small>${esc(hm(s.at))}</small>` : ''}</span></li>`).join('')}</ol>`;
}

const linesOf = (o: any) => (o.lines || []).filter((l: any) => l.issue || l.model || l.device);
const toneOf = (o: any) => {
  const cur = (o.steps || []).find((s: any) => s.current);
  return o.cancelled ? 'x' : cur?.key === 'completed' ? 'ok' : cur?.key === 'received' ? 'new' : cur?.key === 'quotation' ? 'ask' : 'on';
};
const deviceOf = (l: any) => [l.model, l.device].filter(Boolean).join(' · ');
const money = (n: number, b: any) => `${esc(b.currency || '')} ${Number(n || 0).toFixed(b.decimals ?? 3)}`;

// The visit time (o.time, from Odoo): pick it, change it, or answer the parts question. The button
// opens the time picker (components/SlotPicker.astro) on this page.
function timeBox(o: any) {
  const t = o.time;
  if (!t || o.cancelled) return '';
  const [title, line, btn] =
    t.state === 'ask_parts' ? ['A part must be ordered first', 'Tell us if we should order it, then pick your time.', 'Answer'] :
    t.state === 'waiting_parts' ? ["We're getting your part", "You'll pick your visit time here once it arrives.", ''] :
    t.state === 'booked' ? ['Your visit time', t.label, t.can_change ? 'Change time' : ''] :
    ['Pick a time for your visit', 'Choose the day and time our technician comes.', 'Pick a time'];
  return `<div class="tk-timebox ${esc(t.state)}">
      <span class="tk-timeico" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg></span>
      <div><b>${esc(title)}</b><span>${esc(line)}</span></div>
      ${btn ? `<button type="button" class="tk-timebtn" data-pick-time="${esc(o.ref)}">${esc(btn)}</button>` : ''}
    </div>`;
}
// in the list: a small "Pick a time" / "Approve the price" tag (the whole row opens the order, where the button is)
const timeTag = (o: any) => (o.quote && !o.cancelled
  ? `<span class="tk-timetag">${o.quote.lab ? 'Action needed' : 'Approve the price'}</span>`
  : o.time && !o.cancelled && (o.time.state === 'pick' || o.time.state === 'ask_parts')
    ? `<span class="tk-timetag">${o.time.state === 'pick' ? 'Pick a time' : 'Action needed'}</span>` : '');

// The device at our office (o.office, from Odoo): when and by whom it was taken, with what, the dates.
function officeBox(o: any) {
  const f = o.office;
  if (!f || o.cancelled) return '';
  const dates = [
    f.price_by ? `Price by <b>${esc(day(f.price_by))}</b>` : '',
    f.back_by && !f.price_by ? `Back by <b>${esc(day(f.back_by))}</b>` : '',
  ].filter(Boolean).join(' · ');
  return `<div class="tk-timebox office">
      <span class="tk-timeico" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 20V9l8-5 8 5v11"/><path d="M9 20v-6h6v6"/></svg></span>
      <div><b>Your device is at our office</b>
        <span>Taken${f.taken_on ? ` ${esc(when(f.taken_on))}` : ''}${f.technician ? ` by ${esc(f.technician)}` : ''}, with: ${esc(f.accessories || 'the device only')}.</span>
        ${dates ? `<span>${dates}</span>` : ''}</div>
    </div>`;
}

// A new price after the technician's check (o.quote, from Odoo), waiting for the customer: the button
// opens the price on this page (components/PricePicker.astro), the same as the WhatsApp link's page.
function quoteBox(o: any) {
  const q = o.quote;
  if (!q || o.cancelled) return '';
  if (q.lab) {
    // the technician asks to take the device to our lab for a check: the customer's OK first
    return `<div class="tk-timebox ask">
      <span class="tk-timeico" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3"/></svg></span>
      <div><b>May we take your device to our lab?</b><span>A closer check is needed. You'll get the price${q.lab.date ? ` by ${esc(q.lab.date)}` : ''}; nothing is repaired before you approve it.</span></div>
      <button type="button" class="tk-timebtn" data-review-price="${esc(o.ref)}">Answer</button>
    </div>`;
  }
  return `<div class="tk-timebox ask">
      <span class="tk-timeico" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M7 3.5h10a1.5 1.5 0 0 1 1.5 1.5v15l-2.5-1.5-2.5 1.5-2.5-1.5-2.5 1.5-2.5-1.5V5A1.5 1.5 0 0 1 7 3.5z"/><path d="M9 9h6M9 12.5h6"/></svg></span>
      <div><b>New price to approve: ${money(q.total, q)}</b><span>The technician checked your device. Nothing is done before you approve.</span></div>
      <button type="button" class="tk-timebtn" data-review-price="${esc(o.ref)}">Review &amp; approve</button>
    </div>`;
}

/** One order in the list (as on a shop's "Your orders"): tap it for the order's own page. */
function orderRow(o: any) {
  const lines = linesOf(o);
  const steps = o.steps || [];
  const at = Math.max(0, steps.findIndex((s: any) => s.current));
  const first = lines[0];
  const title = first ? `${first.issue || 'Repair'}${first.qty > 1 ? ` ×${first.qty}` : ''}` : (o.summary || 'Repair');
  return `
    <button type="button" class="tk-order tk-orow ${toneOf(o)}" data-order="${esc(o.ref)}" aria-label="Order ${esc(o.ref)}, ${esc(o.status)}. Open the order">
      <span class="tk-ico">${icon(lines.map((l: any) => `${l.device} ${l.model}`).join(' ') || o.summary || '')}</span>
      <span class="tk-rmain">
        <b>${esc(title)}${lines.length > 1 ? ` <small>+${lines.length - 1} more</small>` : ''}</b>
        <span>${esc(first ? deviceOf(first) : o.summary || '')}</span>
        ${o.cancelled ? '' : `<span class="tk-bar" aria-hidden="true"><i style="width:${steps.length ? Math.round(((at + 1) / steps.length) * 100) : 0}%"></i></span>`}
        <small>${esc(o.ref)} · Booked ${esc(when(o.created))}</small>
        ${timeTag(o)}
      </span>
      <span class="tk-rside"><span class="tk-status">${esc(o.status)}</span><i class="tk-chev" aria-hidden="true">›</i></span>
    </button>`;
}

/** The order's own page (as Amazon's or Flipkart's order details): what is happening now, every
 *  step with its time, the visit, the repairs and their price, where, the payment and help. */
function orderDetail(o: any, help: { wa: string; tel: string; back: string }) {
  const lines = linesOf(o);
  const cur = (o.steps || []).find((s: any) => s.current);
  const v = o.cancelled ? null : o.visit;
  const b = o.bill;
  // the booking's steps, with the times we know
  const times: Record<string, string> = { received: o.created, confirmed: o.times?.confirmed || '', completed: o.times?.done || '' };
  const steps = (o.steps || []).map((s: any) => `<li class="${s.done ? 'done' : ''}${s.current ? ' cur' : ''}"><i aria-hidden="true"></i>
      <span><b>${esc(s.label)}</b>${s.done && times[s.key] ? `<small>${esc(when(times[s.key]))}</small>` : s.current ? '<small>Now</small>' : ''}</span></li>`).join('');
  const banner = o.cancelled
    ? `<div class="tk-dbanner x"><b>Cancelled</b><span>This booking was cancelled${o.reason ? `: ${esc(o.reason)}` : ''}. Chat with us on WhatsApp if you need help.</span></div>`
    : `<div class="tk-dbanner ${toneOf(o)}"><b>${esc(o.status)}</b><span>${esc((cur && NOW[cur.key]) || '')}</span>${cur?.key !== 'completed' ? '<span class="tk-live"><i></i>live</span>' : ''}</div>`;
  const items = lines.length ? lines.map((l: any) => `<li><span class="tk-ico sm">${icon(`${l.device} ${l.model}`)}</span>
      <span><b>${esc(l.issue || 'Repair')}${l.qty > 1 ? ` ×${esc(String(l.qty))}` : ''}</b><small>${esc(deviceOf(l))}</small></span></li>`).join('')
    : `<li><span><b>${esc(o.summary || 'Repair')}</b></span></li>`;
  const bill = b
    ? `<ul class="tk-bill">${b.lines.map((l: any) => `<li><span>${esc(l.name)}${l.qty > 1 ? ` ×${esc(String(l.qty))}` : ''}${l.kind === 'part' ? ' <small>part</small>' : ''}</span><b>${money(l.amount, b)}</b></li>`).join('')}</ul>
       ${b.tax_label ? `<ul class="tk-bill"><li><span>${esc(b.tax_label)}</span><b>${money(b.tax, b)}</b></li></ul>` : ''}
       <p class="tk-total"><span>Total${b.tax_label ? ' <small>incl. VAT</small>' : ''}</span><b>${money(b.total, b)}</b></p>
       ${v?.close?.paid ? `<p class="tk-paid">✓ ${esc(v.close.paid)}</p>` : b.state === 'waiting' ? `<p class="tk-muted">Nothing is done before you approve this price.</p>
       <button type="button" class="tk-timebtn tk-billbtn" data-review-price="${esc(o.ref)}">Review &amp; approve</button>` : ''}`
    : '<p class="tk-muted">The technician checks your device first and tells you the price before any work starts.</p>';
  const facts = [
    ['Order', o.ref], ['Job card', o.job_card], ['Booked', when(o.created)], ['Service', o.mode_label], ['Visit', o.slot],
    ['Parts', o.parts?.waiting ? `Waiting for a part${o.parts.expected ? `, expected by ${day(o.parts.expected)}` : ''}` : ''],
    ['Warranty', v?.close?.warranty_until ? `until ${day(v.close.warranty_until)}` : ''],
    ['Your rating', v?.close?.rating ? '★'.repeat(Math.max(0, Math.min(5, Number(v.close.rating)))) : ''],
  ].filter(([, x]) => x).map(([k, x]) => `<li><b>${esc(k)}</b><span>${esc(String(x))}</span></li>`).join('');
  const waText = encodeURIComponent(`Hi Danat Fix, I need help with my order ${o.ref}.`);
  return `
    <div class="tk-detail ${toneOf(o)}">
      <button type="button" class="tk-back" data-order-back="${esc(help.back)}">‹ All orders</button>
      <header class="tk-dhead">
        <div><h2>Order ${esc(o.ref)}</h2><small>Booked ${esc(when(o.created))}</small></div>
        <span class="tk-status">${esc(o.status)}</span>
      </header>
      ${banner}
      ${quoteBox(o)}
      ${officeBox(o)}
      ${timeBox(o)}
      <div class="tk-dgrid">
        <div class="tk-dcol">
          ${o.cancelled ? '' : `<section class="tk-dsec"><h3>Order status</h3><ol class="tk-steps">${steps}</ol></section>`}
          ${v ? `<section class="tk-dsec"><h3>Technician visit</h3>${visitBlock(v)}</section>` : ''}
          <section class="tk-dsec"><h3>${lines.length > 1 ? `${lines.length} repairs` : 'Repair'}</h3><ul class="tk-ditems">${items}</ul></section>
        </div>
        <div class="tk-dcol">
          <section class="tk-dsec"><h3>Price details${b?.state === 'waiting' ? ' <em>waiting for your OK</em>' : ''}</h3>${bill}</section>
          ${o.address ? `<section class="tk-dsec"><h3>Service address</h3><p>${esc(o.address)}</p></section>` : ''}
          <section class="tk-dsec"><h3>Order details</h3><ul class="tk-facts">${facts}</ul></section>
          <section class="tk-dsec tk-help"><h3>Need help with this order?</h3><div>
            ${help.wa ? `<a class="tk-hbtn wa" href="https://wa.me/${esc(help.wa)}?text=${waText}" target="_blank" rel="noopener">Chat on WhatsApp</a>` : ''}
            ${help.tel ? `<a class="tk-hbtn" href="tel:${esc(help.tel)}">Call us</a>` : ''}</div></section>
        </div>
      </div>
    </div>`;
}

/** Every order of /api/my-orders as rows, or the "no bookings yet" box. */
export function orderCards(orders: any[]): string {
  if (!orders.length) return '<div class="tk-empty">No bookings for this number yet. <a href="/services">Book a repair →</a></div>';
  return `<div class="tk-rows">${orders.map(orderRow).join('')}</div>`;
}

/** My orders in a box: the list, and an order's own page once one is tapped. The open order is in
 *  the address (#<prefix><ref>), so the phone's Back button goes back to the list and a reload keeps
 *  it. `set` redraws with fresh data (the pages poll every 15 s) and keeps the open order open.
 *  The help buttons use the box's data-wa / data-tel. */
export function ordersView(list: HTMLElement, opts: { prefix: string; back: string }) {
  let orders: any[] = [];
  let shown = '';
  const help = { wa: list.dataset.wa || '', tel: list.dataset.tel || '', back: opts.back };
  const openRef = () => (location.hash.startsWith('#' + opts.prefix) ? decodeURIComponent(location.hash.slice(1 + opts.prefix.length)) : '');
  const draw = () => {
    const ref = openRef();
    const o = ref ? orders.find((x) => x.ref === ref) : null;
    list.innerHTML = o ? orderDetail(o, help) : orderCards(orders);
    const now = o ? ref : '';
    if (now !== shown) {   // just opened or closed: show it from its top
      shown = now;
      list.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  };
  list.addEventListener('click', (e) => {
    const t = e.target as HTMLElement;
    const row = t.closest<HTMLElement>('[data-order]');
    if (row) { location.hash = opts.prefix + encodeURIComponent(row.dataset.order!); return; }
    if (t.closest('[data-order-back]')) location.hash = opts.back;
  });
  window.addEventListener('hashchange', () => { if (orders.length) draw(); });
  return { set(next: any[]) { orders = next; draw(); } };
}
