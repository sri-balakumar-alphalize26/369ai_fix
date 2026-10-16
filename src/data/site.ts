// Site-wide settings. Replace values here and they update everywhere.
// BRAND: renamed to Danat Fix on the owner's request (2026-09-30). The contact
// details below are still Danat's — replace them with Danat Fix's real ones.
// PROVENANCE: contact details are copied from the Danat Computers project's
// src/data/site.ts, where they are marked verified against danatcomputers.com.
// Only Ruwi's address and phone are confirmed; Sohar and Salalah are city only.

export const site = {
  name: 'Danat Fix', // default brand; the header switcher swaps to '369 ai Fix' (BrandSwitch.astro)
  handle: 'danatfix', // social-post preview handle
  tagline: 'Electronics repair at your doorstep',
  city: 'Muscat',
  country: 'Oman',
  currency: 'OMR ',
  since: 2003,
  email: 'danatruwi@danatcomputers.com',
  phone: { display: '+968 7832 3116', tel: '+96878323116' },
  address: 'Computer Street, Ruwi, PO Box 502, PC 118, Sultanate of Oman',
  branches: ['Ruwi, Muscat', 'Sohar', 'Salalah'],
  whatsapp: '96878323116',
  // Branch addresses and phones as listed on 369ai.biz (Our Offices), 2026-10-01
  branchInfo: [
    { name: 'Ruwi', lines: ['Computer Street, Ruwi', 'P.O. Box 502, PC 118', 'Sultanate of Oman'], phones: ['+968 9792 3077', '+968 9792 2924'], map: 'Computer Street, Ruwi, Muscat, Oman' },
    { name: 'Salalah', lines: ['23rd July Street, near NBO', 'Opposite Sultan Qaboos Mosque', 'Salalah, Sultanate of Oman'], phones: ['+968 9792 3005'], map: '23rd July Street, Salalah, Oman' },
    { name: 'Sohar', lines: ['Al Hambar Street', 'Sohar Souq, near Malabar Paris Restaurant', 'Sohar, Sultanate of Oman'], phones: ['+968 9792 3155'], map: 'Al Hambar Street, Sohar Souq, Sohar, Oman' },
  ],
  // Danat Computers' verified pages (from the DanatComputer project) — swap for Danat Fix's own when they exist
  social: {
    facebook: 'https://www.facebook.com/DanatCSOman/',
    instagram: 'https://www.instagram.com/computersupermarketruwi/',
  },
};

// Prices come from Odoo, per repair (and the visit fee). A repair with no price there (0 or not
// set) shows PRICE_LATER: the technician gives the price after checking the device. Every
// amount on the site is worded here. PRICE is the "no price" value of the site's own lists.
export const PRICE = 0;
export const PRICE_LATER = 'Price after check';
/** A real price (Odoo's 0 means "not set", not "free"). */
export const hasPrice = (n: number | null | undefined): n is number => typeof n === 'number' && Number.isFinite(n) && n > 0;
const r3 = (n: number) => Math.round(n * 1000) / 1000;
/** "OMR 12", or "Price after check" when there is no price. */
export const money = (n?: number | null) => (hasPrice(n) ? `${site.currency}${r3(n)}` : PRICE_LATER);
/** "from OMR 12", or "Price after check" when there is no price. */
export const fromMoney = (n?: number | null) => (hasPrice(n) ? `from ${money(n)}` : PRICE_LATER);
/** The visit fee line: "Visit fee OMR 5", or "Visit fee: price after check". */
export const feeLine = (n?: number | null, label = 'Visit fee') => (hasPrice(n) ? `${label} ${money(n)}` : `${label}: ${PRICE_LATER.toLowerCase()}`);
/** What {price} in Odoo texts becomes (trust points, FAQ answers): the visit fee, else "price after check". */
export const priceWord = (n?: number | null) => (hasPrice(n) ? money(n) : PRICE_LATER.toLowerCase());

export const nav = [
  { href: '/', label: 'Home' },
  { href: '/services', label: 'Services' },
  { href: '/team', label: 'Our Team' },
  { href: '/track', label: 'My Orders' },
];

// One repair flow (no Doorstep / Pickup choice): the technician always comes first. Line 1 is the
// visit, its last step the "fixed on the spot" branch; line 2 is the other branch, when it needs a
// part or more work. The ids keep the shape Odoo's two "Doorstep / pickup cards" lines use.
export const serviceModes = [
  {
    id: 'doorstep',
    title: 'We come to you',
    short: 'Our technician visits at the time you pick',
    eta: 'Technician at your door in about 60 minutes',
    body: 'A technician rides to your home or office with parts and tools. Phones and laptops are fixed in front of you; printers, CCTV and Wi-Fi are installed and serviced on-site.',
    steps: ['Book a slot', 'Technician visits', 'Fixed on the spot ✓'],
  },
  {
    id: 'pickup',
    title: 'Needs a part or more work',
    short: 'Price confirmed with you first',
    eta: 'Back in 24–48 hours',
    body: 'If it cannot be fixed on the spot, the device goes to our lab, is repaired and comes back to the same address.',
    steps: ['Taken to our lab', 'Repaired', 'Delivered back'],
  },
] as const;

export type ServiceModeId = (typeof serviceModes)[number]['id'];
