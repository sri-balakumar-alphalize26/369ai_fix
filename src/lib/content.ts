// The website's own texts, edited in Odoo (Fix Website app, 369ai_fix add-on, website/):
// the home page sections, the device tiles and "most booked" repairs, the site's name and
// contact details, the header menu, the branches, the footer, the Services page wording,
// the coverage areas, the FAQs and the info pages (/page/<slug>). Server-only. Cached per
// host for 5 minutes like the catalogue; when Odoo cannot be reached the last good copy is
// used, and failing that the site's own files (src/data/site.ts, home.ts, reviews.ts,
// coverage.ts, faq.ts), so the pages always render.
import { categories as staticCategories } from '../data/devices';
import { milestones as staticMilestones, homeServices } from '../data/home';
import { photo } from '../data/photos';
import { reviews as staticReviews } from '../data/reviews';
import { nav as staticNav, serviceModes, site, priceWord, PRICE, type ServiceModeId } from '../data/site';
import { coverage as staticCoverage } from '../data/coverage';
import { faqs as staticFaqs, infoPages as staticPages } from '../data/faq';
import { areaGeo as staticGeo } from './areaGeo';
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
};

const TTL_MS = 5 * 60 * 1000;
const cache = new Map<string, { at: number; data: Content }>();
const s = (v: unknown) => (typeof v === 'string' ? v : '');
const sec = (kind: SectionKind, p: Partial<Section>): Section => ({
  kind, eyebrow: '', title: '', title2: '', subtitle: '', text: '', badge: '', button1: '', button1_link: '', button2: '', button2_link: '', lines: [], ...p,
});
const line = (p: Partial<Line>): Line => ({ name: '', value: '', text: '', extra: '', stars: 5, link: '', ...p });
// {price} in Odoo texts: the visit fee ("OMR 5"), or "price after check" when there is none
const fill = (t: string, fee: number) => t.replaceAll('{price}', priceWord(fee));
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
      footer: { about: `${site.tagline}. Phones, laptops, printers, CCTV and Wi-Fi — repaired at your door or picked up and brought back, across ${site.country} since ${site.since}.`,
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
  };
}

function fromOdoo(raw: any): Content {
  const st = raw.site || {};
  const fee = Number(st.visit_fee) || 0;
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
    trust: (cv.trust || []).length ? cv.trust.map((t: any) => fill(s(t), fee)) : sc.trust,
    doorstep: { eta: modes[0].eta, zones: zonesOf('doorstep') }, pickup: { eta: modes[1].eta, zones: zonesOf('pickup') },
    geo: { ...staticGeo, ...odooGeo },
  };
  const faq = (st.faq || []).map((f: any) => ({ q: s(f.q), a: fill(s(f.a), fee) })).filter((f: { q: string }) => f.q);
  const pages: InfoPage[] = (st.pages || []).map((p: any) => ({ title: s(p.title), slug: s(p.slug), column: p.column || 'none', kind: p.kind || 'text', body: s(p.body) }));
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
