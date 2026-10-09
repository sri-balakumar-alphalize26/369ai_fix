// Content for the conversion-focused Home page.
import { site, price, PRICE } from './site';
import { categories } from './devices';

// WhatsApp deep link with a pre-filled message (Danat's verified number).
export const wa = (msg: string) => `https://wa.me/${site.phone.tel.replace('+', '')}?text=${encodeURIComponent(msg)}`;

// ---- Services grid: 4 top services from each of the 9 device types = 36 ----
// PRICING PLACEHOLDER: `from` is PRICE (0) for every service until the client
// supplies real base prices. Set a number per service here and it shows.
const basePrice: Record<string, number> = {};
export const homeServices = categories.flatMap((c) =>
  c.issues.slice(0, 4).map((issue) => ({
    id: `${c.id}-${issue}`,
    cat: c.id,
    catName: c.name,
    icon: c.icon,
    hue: c.hue,
    name: issue,
    from: price(basePrice[`${c.id}-${issue}`] ?? PRICE),
    wa: wa(`Hi Danat Fix, I want to book a ${issue} service for my ${c.name.replace(/ &.*$/, '').replace(/s$/, '').toLowerCase()}.`),
  })),
);

// ---- Company roadmap ----
// Only 2003 is verified (earliest ERP record; "trading since 2003").
// Branch opening years are NOT known — shown as "Year TBC" until the client
// confirms. Do not fill them with guesses.
export const milestones = [
  { year: '2003', title: 'First store opens on Computer Street, Ruwi', text: 'Computer sales and repair in Muscat.', verified: true },
  { year: 'Year TBC', title: 'Sohar branch opens', text: 'Serving Al Batinah.', verified: false },
  { year: 'Year TBC', title: 'Salalah branch opens', text: 'Serving Dhofar.', verified: false },
  { year: 'Today', title: '5,430 products · 249 categories', text: 'Laptops, printers, CCTV, networking and parts in stock.', verified: true },
  { year: 'Now', title: 'Doorstep & pickup repair', text: `Technicians and riders across ${site.country}.`, verified: true },
];

// ---- Awards ---- SAMPLE: none have been supplied by the client.
export const awardsSample = true;
export const awards = [
  { title: 'Award title', by: 'Awarding body', year: 'Year' },
  { title: 'Partner recognition', by: 'Brand partner', year: 'Year' },
  { title: 'Customer choice', by: 'Publication', year: 'Year' },
];
