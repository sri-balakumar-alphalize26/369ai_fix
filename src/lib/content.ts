// The website's own texts, edited in Odoo (Fix Website app, 369ai_fix add-on, website/):
// the home page sections, the device tiles and "most booked" repairs, the site's name and
// contact details, the header menu, the branches and the footer. Server-only. Cached per
// host for 5 minutes like the catalogue; when Odoo cannot be reached the last good copy is
// used, and failing that the site's own files (src/data/site.ts, home.ts, reviews.ts), so
// the pages always render.
import { categories as staticCategories } from '../data/devices';
import { milestones as staticMilestones, homeServices } from '../data/home';
import { photo } from '../data/photos';
import { reviews as staticReviews } from '../data/reviews';
import { nav as staticNav, serviceModes, site, price, PRICE } from '../data/site';
import { odooCall } from './odoo';

export type Line = { name: string; value: string; text: string; extra: string; stars: number; link: string; image?: string };
export type SectionKind = 'hero' | 'services' | 'modes' | 'brands' | 'reviews' | 'milestones' | 'partners' | 'cta';
export type Section = {
  kind: SectionKind; eyebrow: string; title: string; title2: string; subtitle: string; text: string; badge: string;
  button1: string; button1_link: string; button2: string; button2_link: string; lines: Line[];
  video?: string; poster?: string | false;
};
export type Branch = { name: string; lines: string[]; phones: string[]; map: string; hours: string };
export type SiteContent = {
  name: string; tagline: string; phone: string; whatsapp: string; email: string; address: string; hours: string; since: string;
  social: { facebook: string; instagram: string };
  header: { cta: string; cta_link: string; menu: { label: string; link: string }[] };
  quick_links: { label: string; link: string }[];
  branches: Branch[];
  footer: { about: string; copyright: string; credit: string };
};
export type Content = {
  odoo: boolean;
  site: SiteContent;
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
      hours: '', since: String(site.since), social: { facebook: site.social.facebook, instagram: site.social.instagram },
      header: { cta: 'Book a repair', cta_link: '/services#catalog', menu: staticNav.map((n) => ({ label: n.label, link: n.href })) },
      quick_links: [...staticNav.map((n) => ({ label: n.label, link: n.href })),
        { label: 'Get an estimate', link: '/services#catalog' }, { label: 'Check location', link: '/#check-location' },
        { label: 'Book on WhatsApp', link: `https://wa.me/${site.whatsapp}` }],
      branches: site.branchInfo.map((b) => ({ name: b.name, lines: b.lines, phones: b.phones, map: b.map, hours: '' })),
      footer: { about: `${site.tagline}. Phones, laptops, printers, CCTV and Wi-Fi — repaired at your door or picked up and brought back, across ${site.country} since ${site.since}.`,
        copyright: `© {year} ${site.name}. All rights reserved. · Estimates shown as ${price()} — pricing to be announced.`, credit: '' },
    },
    sections: [
      sec('hero', { eyebrow: `Doorstep electronics repair · ${site.country}`, title: 'Your Technology.', title2: 'Fixed Right.',
        subtitle: 'Phone • Laptop • Computer • Printer • CCTV • Networking', button1: 'Book Your Slot', button1_link: '#book-services', button2: 'WhatsApp us',
        video: '/media/kling.mp4', poster: '/media/kling.jpg',
        lines: [line({ value: `${homeServices.length}+`, name: 'services' }), line({ value: String(site.branches.length), name: 'branches' }), line({ value: String(site.since), name: 'since' })] }),
      sec('services', { title: 'What can we fix for you?', subtitle: 'Most booked repairs', text: `Doorstep or pickup · estimate ${price()}`, button1: 'View all services', button1_link: '/services#all' }),
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
    tiles: staticCategories.filter((c) => c.id !== 'printer' && c.id !== 'cctv').map((c) => ({ id: null, name: short(c.name) })),
    brands: [],
    mostBooked: picks,
  };
}

function fromOdoo(raw: any): Content {
  const st = raw.site || {};
  return {
    odoo: true,
    site: {
      name: s(st.name) || site.name, tagline: s(st.tagline), phone: s(st.phone), whatsapp: s(st.whatsapp).replace(/\D/g, ''), email: s(st.email),
      address: s(st.address), hours: s(st.hours), since: s(st.since),
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

/** A WhatsApp link to the site's number with a message, e.g. for "WhatsApp us" buttons. */
export const waLink = (c: SiteContent, msg: string) => `https://wa.me/${c.whatsapp || site.whatsapp}?text=${encodeURIComponent(msg)}`;
