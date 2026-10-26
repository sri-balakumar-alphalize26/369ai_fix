// The website's own texts, edited in Odoo (Fix Website app, 369ai_fix add-on, website/):
// the home page sections, the device tiles and "most booked" repairs, the site's name and
// contact details, the header menu, the branches, the footer, the Services page wording,
// the coverage areas, the FAQs, the info pages (/page/<slug>) and the pop-ups & chat (announcement
// bar, welcome pop-up, flash offer, cookie notice, Spin & Win, chat assistant, "Book your slot"
// slider, "Leaving already?" panel). Server-only. Cached per host for 5 minutes like the
// catalogue; when Odoo cannot be reached the last good copy is used, and failing that the site's
// own files (src/data/site.ts, home.ts, reviews.ts, coverage.ts, faq.ts, popups.ts), so the
// pages always render.
import { categories as staticCategories } from '../data/devices';
import { milestones as staticMilestones, homeServices } from '../data/home';
import { photo } from '../data/photos';
import { reviews as staticReviews } from '../data/reviews';
import { nav as staticNav, serviceModes, site, priceWord, feeLine, PRICE, type ServiceModeId } from '../data/site';
import { coverage as staticCoverage } from '../data/coverage';
import { faqs as staticFaqs, infoPages as staticPages } from '../data/faq';
import { areaGeo as staticGeo } from './areaGeo';
import { STATIC_POPUPS, STATIC_WHEEL, STATIC_BOT, STATIC_ENGAGE } from '../data/popups';
import { odooCall } from './odoo';

export type Line = { name: string; value: string; text: string; extra: string; stars: number; link: string; image?: string };
export type SectionKind = 'hero' | 'services' | 'modes' | 'brands' | 'reviews' | 'milestones' | 'partners' | 'cta';
export type Section = {
  kind: SectionKind; eyebrow: string; title: string; title2: string; subtitle: string; text: string; badge: string;
  button1: string; button1_link: string; button2: string; button2_link: string; lines: Line[];
  video?: string; poster?: string | false;
  popular?: { name: string; link: string }[];   // top banner: the "Popular:" chips under the search
};
export type Branch = { name: string; lines: string[]; phones: string[]; map: string; hours: string };
export type SiteContent = {
  name: string; tagline: string; phone: string; whatsapp: string; email: string; address: string; hours: string; since: string;
  visit_fee: number;   // the visit fee product's price in Odoo (0 = none set: "price after check")
  social: { facebook: string; instagram: string };
  header: { cta: string; cta_link: string; menu: { label: string; link: string }[] };
  quick_links: { label: string; link: string }[];
  branches: Branch[];
  footer: { about: string; copyright: string; credit: string };
};
export type Zone = { name: string; areas: string[]; pin: [number, number] | null };
export type ModeCard = { id: ServiceModeId; title: string; short: string; eta: string; steps: string[] };
export type Coverage = {
  eyebrow: string; title: string; trust: string[];
  doorstep: { eta: string; zones: Zone[] }; pickup: { eta: string; zones: Zone[] };
  geo: Record<string, [number, number]>;   // area → map position, for "check my location"
};
export type ServicesPage = { eyebrow: string; title: string; title2: string; lead: string; modes_eyebrow: string; modes_title: string; fee_label: string };
export type InfoPage = { title: string; slug: string; column: 'company' | 'help' | 'policies' | 'none'; kind: 'text' | 'contact' | 'areas' | 'faq'; body: string };
// Pop-ups & chat (Fix Website ▸ Pop-ups & chat). Texts may carry placeholders: `{site}`, `{fee}` and
// `{price}` are filled here (fill()); the rest by the component or in the browser (src/data/popups.ts).
export type Popups = {
  ann: { show: boolean; text: string; button: string; link: string; speed_s: number };
  welcome: { type: 'slot' | 'spin' | 'flash' | 'none'; delay_ms: number; flash_delay_ms: number; snooze_days: number };
  flash: { badge: string; title: string; body: string; code: string; button: string; button_link: string; wa_button: string; wa_msg: string; later: string };
  cookie: { show: boolean; title: string; text: string; decline: string; accept: string; delay_ms: number };
};
export type WheelIcon = 'diag' | 'pick' | 'clean' | 'fast' | 'data' | 'guard';
// A slice's `id` is Odoo's prize row: Odoo picks the prize, the wheel lands on that id (0 = the site's own slices)
export type WheelSlice = { id: number; top: string; label: string; full: string; code: string; icon: WheelIcon; color: string; text_color: string };
export type Wheel = {
  show: boolean; every_days: number;
  tab: string; eyebrow: string; title: string; title2: string; subtitle: string; spin: string; later: string; won: string; note: string;
  book: string; wa: string; wa_msg: string; slices: WheelSlice[];
};
export type BotIntent = 'book' | 'area' | 'price' | 'time' | 'contact' | 'hours' | 'human' | 'menu';
export type BotAnswer = 'book' | 'dev' | 'iss' | 'area' | 'price' | 'time' | 'contact' | 'hours' | 'human' | 'menu' | 'found' | 'fallback';
export type Bot = {
  name: string; status: string; greeting: string; placeholder: string; tip: string; wa_tip: string; wa_msg: string;
  replies: { label: string; intent: string }[]; answers: Record<BotAnswer, string>;
};
// A slide / exit tile belongs to a device category: Odoo rows by `category_id` (the catalogue's
// odooId), the site's own rows by `cat` (the catalogue's id)
export type EngageSlide = { category_id: number | null; cat: string; category: string; title: string; title2: string; pitch: string; perks: string[] };
export type ExitTile = { category_id: number | null; cat: string; category: string; label: string };
export type Engage = {
  eyebrow: string; title2_generic: string; perks_generic: string[]; from_label: string; slide_ms: number; idle_s: number; still_s: number; wa_msg: string;
  form: { pill: string; title: string; subtitle: string; privacy: string; send: string; all: string; all_link: string; features: { title: string; small: string }[] };
  slides: EngageSlide[];
  exit: { title: string; status: string; text: string; button: string; wa_msg: string; tile_msg: string; link: string; link_label: string; tiles: ExitTile[] };
};
export type Content = {
  odoo: boolean;
  site: SiteContent;
  services: ServicesPage;
  modes: ModeCard[];
  coverage: Coverage;
  faq: { q: string; a: string }[];
  pages: InfoPage[];   // only the ones that show (a text page needs text)
  sections: Section[];
  tiles: { id: number | null; name: string }[];
  brands: { id: number | null; name: string; caption: string; color: string; logo: string | false }[];
  mostBooked: { id: number | null; name: string; price: number; categories: string[]; image: string | false }[];
  popups: Popups;   // announcement bar, welcome pop-up, flash offer, cookie notice
  wheel: Wheel;     // Spin & Win
  bot: Bot;         // chat assistant
  engage: Engage;   // "Book your slot" slider and the "Leaving already?" panel
};

const TTL_MS = 5 * 60 * 1000;
const cache = new Map<string, { at: number; data: Content }>();
const s = (v: unknown) => (typeof v === 'string' ? v : '');
const sec = (kind: SectionKind, p: Partial<Section>): Section => ({
  kind, eyebrow: '', title: '', title2: '', subtitle: '', text: '', badge: '', button1: '', button1_link: '', button2: '', button2_link: '', lines: [], ...p,
});
const line = (p: Partial<Line>): Line => ({ name: '', value: '', text: '', extra: '', stars: 5, link: '', ...p });
// Placeholders filled on the server: `{site}` the website's name (the Odoo name, so the brand
// switch's name swap keeps working), `{fee}` the visit-fee line ("Visit fee OMR 5"), `{price}` the
// visit fee ("OMR 5"), or "price after check" when there is none
export type Fill = { site: string; fee: string; price: string };
const fillOf = (name: string, fee: number): Fill => ({ site: name, fee: feeLine(fee), price: priceWord(fee) });
const fill = (t: string, v: Partial<Fill>) => Object.entries(v).reduce((out, [k, val]) => out.replaceAll(`{${k}}`, val ?? ''), t);
/** fill() on every string inside an object or list (lists of rows included). */
const fillDeep = <T,>(x: T, v: Partial<Fill>): T => {
  if (typeof x === 'string') return fill(x, v) as T;
  if (Array.isArray(x)) return x.map((i) => fillDeep(i, v)) as T;
  if (x && typeof x === 'object') return Object.fromEntries(Object.entries(x).map(([k, i]) => [k, fillDeep(i, v)])) as T;
  return x;
};
// The chat answers keep `{price}` for the browser: there it is the repair's own price
const fillPopups = (p: { popups: Popups; wheel: Wheel; bot: Bot; engage: Engage }, v: Fill) => ({
  popups: fillDeep(p.popups, v), wheel: fillDeep(p.wheel, v), engage: fillDeep(p.engage, v),
  bot: { ...fillDeep({ ...p.bot, answers: undefined }, v), answers: fillDeep(p.bot.answers, { site: v.site, fee: v.fee }) } as Bot,
});
/** Odoo's single fields over the site's own: '' / missing = the site's wording, a number must be
 * above 0, a flag must be a real true/false. Nested objects likewise; lists are merged by the caller. */
const merge = <T extends Record<string, any>>(o: any, st: T): T => {
  const out: any = { ...st };
  for (const [k, v] of Object.entries(st)) {
    const x = o?.[k];
    if (typeof v === 'string') out[k] = s(x) || v;
    else if (typeof v === 'number') out[k] = typeof x === 'number' && x > 0 ? x : v;
    else if (typeof v === 'boolean') out[k] = typeof x === 'boolean' ? x : v;
    else if (v && typeof v === 'object' && !Array.isArray(v)) out[k] = merge(x, v);
  }
  return out;
};
const strList = (x: unknown, st: string[]) => (Array.isArray(x) && x.length ? x.map(s).filter(Boolean) : st);
const rows = <R,>(x: unknown, st: R[], row: (r: any, i: number) => R): R[] => (Array.isArray(x) && x.length ? x.map((r, i) => row(r, i)) : st);
const idOf = (x: unknown) => (typeof x === 'number' && x > 0 ? x : Array.isArray(x) && typeof x[0] === 'number' ? x[0] : null);
const WHEEL_ICONS: WheelIcon[] = ['diag', 'pick', 'clean', 'fast', 'data', 'guard'];
/** Pop-ups & chat from Odoo's `site` group, every piece falling back to the site's own. */
function popupsFromOdoo(st: any) {
  const p = st.popups || {}, w = st.wheel || {}, b = st.bot || {}, e = st.engage || {};
  const wt = s(p.welcome?.type);
  const popups: Popups = merge(p, STATIC_POPUPS);
  popups.welcome.type = wt === 'slot' || wt === 'spin' || wt === 'flash' || wt === 'none' ? wt : STATIC_POPUPS.welcome.type;
  const wheel: Wheel = { ...merge(w, STATIC_WHEEL), slices: rows(w.slices, STATIC_WHEEL.slices, (r, i) => ({
    id: idOf(r.id) ?? 0, top: s(r.top), label: s(r.label), full: s(r.full) || `${s(r.top)} ${s(r.label)}`.trim(), code: s(r.code),
    icon: WHEEL_ICONS.includes(r.icon) ? r.icon : WHEEL_ICONS[i % WHEEL_ICONS.length],
    color: s(r.color) || STATIC_WHEEL.slices[i % STATIC_WHEEL.slices.length].color,
    text_color: s(r.text_color) || STATIC_WHEEL.slices[i % STATIC_WHEEL.slices.length].text_color })) };
  const bot: Bot = { ...merge(b, STATIC_BOT), answers: merge(b.answers, STATIC_BOT.answers),
    replies: rows(b.replies, STATIC_BOT.replies, (r) => ({ label: s(r.label), intent: s(r.intent) })).filter((r) => r.label && r.intent) };
  const engage: Engage = { ...merge(e, STATIC_ENGAGE),
    perks_generic: strList(e.perks_generic, STATIC_ENGAGE.perks_generic),
    form: { ...merge(e.form, STATIC_ENGAGE.form), features: rows(e.form?.features, STATIC_ENGAGE.form.features, (r) => ({ title: s(r.title), small: s(r.small) })) },
    slides: rows(e.slides, STATIC_ENGAGE.slides, (r) => ({ category_id: idOf(r.category_id), cat: '', category: s(r.category),
      title: s(r.title), title2: s(r.title2), pitch: s(r.pitch), perks: strList(r.perks, []) })),
    exit: { ...merge(e.exit, STATIC_ENGAGE.exit), tiles: rows(e.exit?.tiles, STATIC_ENGAGE.exit.tiles, (r) => ({
      category_id: idOf(r.category_id), cat: '', category: s(r.category), label: s(r.label) })) } };
  return { popups, wheel, bot, engage };
}
const showable = (p: InfoPage) => !!p.slug && (p.kind !== 'text' || !!p.body.replace(/<[^>]*>/g, '').trim());
// Map centre for each zone, in zone order (Muscat, Sohar/Al Batinah, Salalah/Dhofar)
const ZONE_PINS: [number, number][] = [[23.593, 58.556], [24.347, 56.709], [17.019, 54.089]];

const STATIC_SERVICES: ServicesPage = {
  eyebrow: 'Services', title: 'Doorstep repair,', title2: 'on the spot or in our lab.',
  lead: 'Our technician comes to you first. Check that we reach your area, then pick your device and repairs.',
  modes_eyebrow: 'How it works', modes_title: 'We come to you first', fee_label: 'Visit fee',
};
const staticModes = (): ModeCard[] => serviceModes.map((m) => ({ id: m.id, title: m.title, short: m.short, eta: m.eta, steps: [...m.steps] }));
const staticCoverageOf = (): Coverage => {
  const zones = (id: ServiceModeId) => staticCoverage[id].zones.map((z, k) => ({ name: z.name, areas: [...z.areas], pin: ZONE_PINS[k] ?? null }));
  return {
    eyebrow: 'Check your area', title: 'Where we cover',
    trust: ['Diagnosis before any work', `Visit fee: ${priceWord(PRICE)}`, 'Updates on WhatsApp', 'Not listed? Book anyway — we confirm'],
    doorstep: { eta: staticCoverage.doorstep.eta, zones: zones('doorstep') }, pickup: { eta: staticCoverage.pickup.eta, zones: zones('pickup') },
    geo: { ...staticGeo },
  };
};

export type RepairFlow = { title: string; short: string; eta: string; shared: string[]; spot: string;
  lab: { title: string; note: string; eta: string; steps: string[] } };
/** The one repair flow, from the two card lines: the visit (its last step = fixed on the spot)
 * and the branch for a part or more work (to our lab and back). Used by Home and Services. */
export function repairFlow(modes: ModeCard[]): RepairFlow {
  const [visit, lab] = [modes[0] ?? staticModes()[0], modes[1] ?? staticModes()[1]];
  const steps = visit.steps.length > 1 ? visit.steps : staticModes()[0].steps;
  return { title: visit.title, short: visit.short, eta: visit.eta, shared: steps.slice(0, -1), spot: steps[steps.length - 1],
    lab: { title: lab.title, note: lab.short, eta: lab.eta, steps: lab.steps } };
}

/** "We serve Muscat, Al Batinah and Dhofar from our Ruwi, Sohar and Salalah branches." from the zone names. */
export function coverLine(c: Coverage): string {
  const zones = c.pickup.zones.length ? c.pickup.zones : c.doorstep.zones;
  const and = (xs: string[]) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}` : xs[0] ?? '');
  const regions = zones.map((z) => z.name.replace(/ \(.*\)/, ''));
  const branches = zones.map((z) => z.name.match(/\((.*?)(?: branch)?\)/)?.[1] ?? z.name.replace(/ \(.*\)/, ''));
  return regions.length ? `We serve ${and(regions)} from our ${and(branches)} branch${branches.length > 1 ? 'es' : ''}.` : '';
}

/** The site as it is in code: what shows when Odoo has never answered. */
export function staticContent(): Content {
  const short = (n: string) => n.replace(' & MacBooks', '').replace(' & All-in-ones', '').replace(' & iPads', '').replace(' Installation', '').replace(' & Wi-Fi', '');
  const picks = ['screen', 'battery', 'tab-screen', 'lap-screen', 'lap-keyboard', 'desk-power-on', 'desk-ssd', 'water'].map((ph) => {
    const key = Object.keys(photo).find((k) => photo[k] === ph)!;
    const [cid, iss] = key.split(':');
    const cat = staticCategories.find((c) => c.id === cid)!;
    return { id: null, name: iss, price: PRICE, categories: [cat.name], image: `/media/repairs/${ph}.jpg` as string | false };
  });
  return {
    odoo: false,
    site: {
      name: site.name, tagline: site.tagline, phone: site.phone.display, whatsapp: site.whatsapp, email: site.email, address: site.address,
      hours: '', since: String(site.since), visit_fee: PRICE, social: { facebook: site.social.facebook, instagram: site.social.instagram },
      header: { cta: 'Book a repair', cta_link: '/services#catalog', menu: staticNav.map((n) => ({ label: n.label, link: n.href })) },
      quick_links: [...staticNav.map((n) => ({ label: n.label, link: n.href })),
        { label: 'Get an estimate', link: '/services#catalog' }, { label: 'Check location', link: '/#check-location' },
        { label: 'Book on WhatsApp', link: `https://wa.me/${site.whatsapp}` }],
      branches: site.branchInfo.map((b) => ({ name: b.name, lines: b.lines, phones: b.phones, map: b.map, hours: '' })),
      footer: { about: `${site.tagline}, across ${site.country} since ${site.since}.`,
        copyright: `© {year} ${site.name}. All rights reserved.`, credit: '' },
    },
    sections: [
      sec('hero', { eyebrow: `Doorstep electronics repair · ${site.country}`, title: 'Your Technology.', title2: 'Fixed Right.',
        subtitle: 'Phone • Laptop • Computer • Printer • CCTV • Networking', button1: 'Book Your Slot', button1_link: '#book-services', button2: 'WhatsApp us',
        video: '/media/kling.mp4', poster: '/media/kling.jpg',
        popular: [{ name: 'Laptop Repair', link: '/services?cat=laptop#catalog' }, { name: 'iPhone Repair', link: '/services?cat=mobile&q=iPhone#catalog' }, { name: 'Printer Repair', link: '/services?cat=printer#catalog' }, { name: 'CCTV Installation', link: '/services?cat=cctv#catalog' }, { name: 'Data Recovery', link: '/services?cat=data#catalog' }],
        lines: [line({ value: `${homeServices.length}+`, name: 'services' }), line({ value: String(site.branches.length), name: 'branches' }), line({ value: String(site.since), name: 'since' })] }),
      sec('services', { title: 'What can we fix for you?', subtitle: 'Most booked repairs', text: 'Doorstep or pickup · price confirmed before any work', button1: 'View all services', button1_link: '/services#all' }),
      sec('modes', { button1: 'Check your area →', button1_link: '/services#coverage',
        lines: serviceModes.map((m) => line({ name: m.title, extra: m.short, value: m.eta ?? '', text: m.steps.join('\n') })) }),
      sec('brands', { eyebrow: 'Brands we repair', title: 'All the big names,', title2: 'one trusted fix.' }),
      sec('reviews', { eyebrow: 'Testimonials', title: 'What our clients say', text: `Doorstep visits, pickups and installs across ${site.country} — in our customers’ words.`,
        lines: staticReviews.map((r) => line({ name: r.name, value: r.area, extra: r.service, stars: r.rating, text: r.text })) }),
      sec('milestones', { eyebrow: 'Our journey', title: 'From one shop to doorstep repair', text: `Years marked “TBC” are waiting for confirmation from ${site.name}.`,
        lines: staticMilestones.map((m) => line({ value: m.year, name: m.title, text: m.text })) }),
      sec('partners', { eyebrow: 'Trusted partners', title: 'Leading brands,', title2: 'in safe hands', text: `Companies that trust ${site.name} with their devices, networks and IT support.`,
        lines: [['Alphalize', 'alphalize'], ['369 ai.Biz', '369aibiz'], ['Nex Genn POS', 'nexgenpos']].map(([n, f]) => line({ name: n, image: `/brand/partners/${f}.png` })) }),
      sec('cta', { eyebrow: "Let's get started", title: 'Need a', title2: 'repair or service?',
        text: 'From phones to laptops, printers to networking — our team is ready to help you get back to what matters.', button1: 'Book a repair', button1_link: '/services#catalog',
        lines: [line({ name: `Since ${site.since}` }), line({ name: 'Doorstep & pickup' }), line({ name: 'Updates on WhatsApp' })] }),
    ],
    services: STATIC_SERVICES,
    modes: staticModes(),
    coverage: staticCoverageOf(),
    faq: staticFaqs,
    pages: staticPages.map((p) => ({ ...p })).filter(showable),
    tiles: staticCategories.filter((c) => c.id !== 'printer' && c.id !== 'cctv').map((c) => ({ id: null, name: short(c.name) })),
    brands: [],
    mostBooked: picks,
    ...fillPopups({ popups: STATIC_POPUPS, wheel: STATIC_WHEEL, bot: STATIC_BOT, engage: STATIC_ENGAGE }, fillOf(site.name, PRICE)),
  };
}

function fromOdoo(raw: any): Content {
  const st = raw.site || {};
  const fee = Number(st.visit_fee) || 0;
  const fl = fillOf(s(st.name) || site.name, fee);
  // Empty in Odoo = the site's own wording, so a blank field never leaves a hole
  const sv = st.services || {};
  const services = Object.fromEntries(Object.entries(STATIC_SERVICES).map(([k, v]) => [k, s(sv[k]) || v])) as ServicesPage;
  const cards: any[] = raw.modes || [];
  const modes = staticModes().map((m, i) => {
    const c = cards[i];
    if (!c) return m;
    const steps = (c.steps || []).map(s).filter(Boolean);
    return { id: m.id, title: s(c.title) || m.title, short: s(c.short) || m.short, eta: s(c.eta) || m.eta, steps: steps.length ? steps : m.steps };
  });
  const cv = st.coverage || {};
  const sc = staticCoverageOf();
  const zonesOf = (id: ServiceModeId) => {
    const zs: Zone[] = (cv[id]?.zones || []).map((z: any) => ({ name: s(z.name), areas: (z.areas || []).map(s).filter(Boolean),
      pin: Array.isArray(z.pin) && (z.pin[0] || z.pin[1]) ? [Number(z.pin[0]), Number(z.pin[1])] as [number, number] : null }));
    return zs.length ? zs : sc[id].zones;
  };
  const odooGeo = Object.fromEntries(Object.entries(cv.geo || {}).map(([n, p]: [string, any]) => [n, [Number(p[0]), Number(p[1])] as [number, number]]));
  const coverage: Coverage = {
    eyebrow: s(cv.eyebrow) || sc.eyebrow, title: s(cv.title) || sc.title,
    trust: (cv.trust || []).length ? cv.trust.map((t: any) => fill(s(t), fl)) : sc.trust,
    doorstep: { eta: modes[0].eta, zones: zonesOf('doorstep') }, pickup: { eta: modes[1].eta, zones: zonesOf('pickup') },
    geo: { ...staticGeo, ...odooGeo },
  };
  const faq = (st.faq || []).map((f: any) => ({ q: s(f.q), a: fill(s(f.a), fl) })).filter((f: { q: string }) => f.q);
  // a text page Odoo has no text for yet (e.g. the policies) shows the site's own copy until it does
  const ownBody = (slug: string) => staticPages.find((x) => x.slug === slug)?.body || '';
  const pages: InfoPage[] = (st.pages || []).map((p: any) => ({ title: s(p.title), slug: s(p.slug), column: p.column || 'none', kind: p.kind || 'text',
    body: s(p.body).replace(/<[^>]*>/g, '').trim() ? s(p.body) : (p.kind || 'text') === 'text' ? ownBody(s(p.slug)) : s(p.body) }));
  return {
    services, modes, coverage,
    faq: Array.isArray(st.faq) ? faq : staticFaqs,
    pages: (Array.isArray(st.pages) ? pages : staticPages.map((p) => ({ ...p }))).filter(showable),
    odoo: true,
    site: {
      name: s(st.name) || site.name, tagline: s(st.tagline), phone: s(st.phone), whatsapp: s(st.whatsapp).replace(/\D/g, ''), email: s(st.email),
      address: s(st.address), hours: s(st.hours), since: s(st.since), visit_fee: fee,
      social: { facebook: s(st.social?.facebook), instagram: s(st.social?.instagram) },
      header: { cta: s(st.header?.cta), cta_link: s(st.header?.cta_link), menu: (st.header?.menu || []).map((m: any) => ({ label: s(m.label), link: s(m.link) })) },
      quick_links: (st.quick_links || []).map((m: any) => ({ label: s(m.label), link: s(m.link) })),
      branches: (st.branches || []).map((b: any) => ({ name: s(b.name), lines: b.lines || [], phones: b.phones || [], map: s(b.map), hours: s(b.hours) })),
      footer: { about: s(st.footer?.about), copyright: s(st.footer?.copyright), credit: s(st.footer?.credit) },
    },
    sections: (raw.home?.sections || []).map((x: any) => sec(x.kind, {
      eyebrow: s(x.eyebrow), title: s(x.title), title2: s(x.title2), subtitle: s(x.subtitle), text: s(x.text), badge: s(x.badge),
      button1: s(x.button1), button1_link: s(x.button1_link), button2: s(x.button2), button2_link: s(x.button2_link),
      video: s(x.video), poster: s(x.poster) || false,
      popular: Array.isArray(x.popular) ? x.popular.map((p: any) => ({ name: s(p.name), link: s(p.link) })).filter((p: { name: string }) => p.name) : undefined,
      lines: (x.lines || []).map((l: any) => line({ name: s(l.name), value: s(l.value), text: s(l.text), extra: s(l.extra), stars: Number(l.stars) || 0, link: s(l.link), image: s(l.image) || undefined })),
    })),
    tiles: (raw.tiles || []).map((t: any) => ({ id: t.id, name: s(t.name) })),
    brands: (raw.brands || []).map((b: any) => ({ id: b.id, name: s(b.name), caption: s(b.caption), color: s(b.color), logo: s(b.logo) || false })),
    mostBooked: (raw.most_booked || []).map((p: any) => ({ id: p.id, name: s(p.name), price: Number(p.price) || 0, categories: p.categories || [], image: s(p.image) || false })),
    ...fillPopups(popupsFromOdoo(st), fl),
  };
}

export async function getContent(host: string): Promise<Content> {
  const hit = cache.get(host);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.data;
  try {
    const raw = await odooCall<any>(host, 'online.service.order', 'website_content', { host });
    if (!raw?.ok) throw new Error(raw?.error || 'content refused');
    const data = fromOdoo(raw);
    if (!data.sections.length) throw new Error('no home page');
    cache.set(host, { at: Date.now(), data });
    return data;
  } catch (e) {
    console.warn('[content] Odoo not reachable:', (e as Error).message);
    const data = hit?.data ?? staticContent();
    cache.set(host, { at: Date.now() - TTL_MS + 60_000, data });   // try Odoo again in a minute
    return data;
  }
}

export type Contact = { display: string; tel: string; wa: string };
/** The site's phone and WhatsApp number, from Odoo (Website Details) else the site's own:
 * the phone as shown, the same for tel: links (+ and digits), and the WhatsApp digits for wa.me. */
export function contactOf(c?: SiteContent): Contact {
  const display = c?.phone || site.phone.display;
  return { display, tel: display.replace(/[^+\d]/g, ''), wa: c?.whatsapp || site.whatsapp };
}

/** A WhatsApp link to the site's number with a message, e.g. for "WhatsApp us" buttons. */
export const waLink = (c: SiteContent, msg: string) => `https://wa.me/${contactOf(c).wa}?text=${encodeURIComponent(msg)}`;
