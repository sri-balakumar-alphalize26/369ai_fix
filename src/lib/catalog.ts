// The booking wizard's catalogue: device category > brand > series > model and the
// repair services for each device, from Odoo (369ai_fix_web_booking.website_catalog).
// Server-only. Cached per host for 5 minutes; when Odoo cannot be reached the last good
// copy is used, and failing that the site's own lists (src/data/devices.ts) - then the
// wizard books the old way (text only, WhatsApp).
import { categories as staticCategories, type Icon } from '../data/devices';
import { PRICE } from '../data/site';
import { odooCall } from './odoo';

export type WzService = { id: number | null; name: string; price: number | null; b: number | null; s: number | null; m: number | null };
export type WzModel = { id: number | null; name: string; series: string; seriesId: number | null };
export type WzBrand = { id: string; odooId: number | null; name: string; hue: number; models: string[]; items: WzModel[] };
export type WzCategory = {
  id: string; odooId: number | null; name: string; short: string; icon: Icon; hue: number; onsiteOnly?: boolean;
  issues: string[]; services: WzService[]; brands: WzBrand[];
};
export type Catalog = { odoo: boolean; categories: WzCategory[]; totals: { categories: number; brands: number; models: number } };

// Odoo's category names -> the website's own look for that category.
const LOOK: Record<string, string> = {
  'Mobile Phone': 'mobile', Tablet: 'tablet', Laptop: 'laptop', Desktop: 'desktop', Printer: 'printer',
  'CCTV Installation': 'cctv', 'Networking & Wi-Fi': 'network', 'Data Recovery': 'data', 'IT Support': 'itsupport',
};
const TTL_MS = 5 * 60 * 1000;
const cache = new Map<string, { at: number; data: Catalog }>();

const slug = (s: string) => s.toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'x';
const hueOf = (s: string) => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 360, 7);

function totalsOf(categories: WzCategory[]) {
  return {
    categories: categories.length,
    brands: categories.reduce((n, c) => n + c.brands.length, 0),
    models: categories.reduce((n, c) => n + c.brands.reduce((m, b) => m + b.models.length, 0), 0),
  };
}

export function staticCatalog(): Catalog {
  const categories: WzCategory[] = staticCategories.map((c) => ({
    id: c.id, odooId: null, name: c.name, short: c.short, icon: c.icon, hue: c.hue, onsiteOnly: c.onsiteOnly,
    issues: c.issues,
    services: c.issues.map((name) => ({ id: null, name, price: PRICE, b: null, s: null, m: null })),
    brands: c.brands.map((b) => ({
      id: b.id, odooId: null, name: b.name, hue: b.hue, models: b.models,
      items: b.models.map((m) => ({ id: null, name: m, series: '', seriesId: null })),
    })),
  }));
  return { odoo: false, categories, totals: totalsOf(categories) };
}

function fromOdoo(raw: any): Catalog {
  const looks = new Map(staticCategories.map((c) => [c.id, c]));
  const out: WzCategory[] = [];
  for (const cat of raw.categories || []) {
    const services: WzService[] = (cat.services || []).map((s: any) => ({
      id: s.id, name: s.name, price: typeof s.price === 'number' ? s.price : null,
      b: s.brand_id || null, s: s.series_id || null, m: s.model_id || null,
    }));
    if (!services.length) continue;                    // nothing to book for this device
    const look = looks.get(LOOK[cat.name] || '');
    const used = new Set<string>();
    const brands: WzBrand[] = (cat.brands || []).map((b: any) => {
      let id = slug(b.name);
      while (used.has(id)) id += '-' + b.id;
      used.add(id);
      const items: WzModel[] = (b.series || []).flatMap((s: any) =>
        (s.models || []).map((m: any) => ({ id: m.id, name: m.name, series: s.name, seriesId: s.id })));
      const known = look?.brands.find((x) => x.name.toLowerCase() === String(b.name).toLowerCase());
      return { id, odooId: b.id, name: b.name, hue: known?.hue ?? hueOf(b.name), models: items.map((i) => i.name), items };
    }).filter((b: WzBrand) => b.items.length);
    out.push({
      id: look?.id || slug(cat.name),
      odooId: cat.id,
      name: look?.name || cat.name,
      short: look?.short || '',
      icon: look?.icon || 'support',
      hue: look?.hue ?? hueOf(cat.name),
      onsiteOnly: look?.onsiteOnly,
      // the general repairs (not tied to one brand or model) are the wizard's list
      issues: [...new Set(services.filter((s) => !s.b && !s.s && !s.m).map((s) => s.name))],
      services,
      brands,
    });
  }
  // the website's own order first, then anything new staff added in Odoo
  const order = staticCategories.map((c) => c.id);
  out.sort((a, b) => (order.indexOf(a.id) + 1 || 99) - (order.indexOf(b.id) + 1 || 99));
  return { odoo: true, categories: out, totals: totalsOf(out) };
}

export async function getCatalog(host: string): Promise<Catalog> {
  const hit = cache.get(host);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.data;
  try {
    const raw = await odooCall<any>(host, 'online.service.order', 'website_catalog', { host });
    if (!raw?.ok) throw new Error(raw?.error || 'catalogue refused');
    const data = fromOdoo(raw);
    if (!data.categories.length) throw new Error('empty catalogue');
    cache.set(host, { at: Date.now(), data });
    return data;
  } catch (e) {
    console.warn('[catalog] Odoo not reachable:', (e as Error).message);
    const data = hit?.data ?? staticCatalog();         // last good copy, else the site lists
    // try Odoo again in a minute, not on every page view (each try can wait 8 s)
    cache.set(host, { at: Date.now() - TTL_MS + 60_000, data });
    return data;
  }
}
