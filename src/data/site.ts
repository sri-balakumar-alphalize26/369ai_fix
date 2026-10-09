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

// Manager instruction: no real prices for now (shown as OMR 0). Every amount on the site
// comes from here, so switching to real pricing later is one change.
export const PRICE = 0;
export const price = (amount: number = PRICE) => `${site.currency}${amount}`;

export const nav = [
  { href: '/', label: 'Home' },
  { href: '/services', label: 'Services' },
  { href: '/team', label: 'Our Team' },
];

export const serviceModes = [
  {
    id: 'doorstep',
    title: 'Doorstep Service',
    short: 'We repair it at your door',
    body: 'A technician rides to your home or office with parts and tools. Phones and laptops are fixed in front of you; printers, CCTV and Wi-Fi are installed and serviced on-site.',
    steps: ['Book a slot', 'Technician arrives', 'Repaired on the spot'],
  },
  {
    id: 'pickup',
    title: 'Pickup & Service',
    short: 'We collect, repair and return it',
    body: 'A rider collects the phone, laptop, printer or drive, our lab repairs it, and it comes back to the same address.',
    steps: ['Rider picks up', 'Repaired in our lab', 'Delivered back'],
  },
] as const;

export type ServiceModeId = (typeof serviceModes)[number]['id'];
