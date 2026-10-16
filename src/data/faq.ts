// Common questions, answered from how this site's service actually works. Edited in Odoo
// (Fix Website ▸ FAQs); this is the copy shown when Odoo has never answered.
import { priceWord, site } from './site';

export const faqs = [
  { q: 'Is there a charge if you only inspect the device?', a: `The technician checks your device and tells you the price before any work starts — nothing is done without your OK. Visit fee: ${priceWord(0)}.` },
  { q: 'How long does a repair take?', a: 'Most phone and laptop repairs are done on the spot during a doorstep visit. Pickup repairs come back in 24–48 hours; board-level work can take longer and we tell you upfront.' },
  { q: 'Which devices can be repaired at my door?', a: 'Phones, tablets, laptops, desktops and printers can be done at your door or picked up. CCTV and networking are always installed on-site.' },
  { q: 'Is my data safe?', a: 'Your data stays on your device. We only access what the repair needs, and data recovery jobs are handled in our lab.' },
  { q: 'Which areas do you cover?', a: `Areas around our ${site.branches.length} branches — ${site.branches.join(', ')}. Check your area in the coverage section above.` },
];

// Info pages at /page/<slug> (Fix Website ▸ Info Pages). A text page without text is not shown.
export const infoPages = [
  { title: 'About us', slug: 'about', column: 'company', kind: 'text',
    body: '<p>Danat Fix is the repair service of Danat Computers, selling and repairing computers on Computer Street, Ruwi, since 2003.</p><p>Today our technicians repair phones, tablets, laptops, desktops and printers, and install CCTV and Wi-Fi, at your door or after picking the device up, from our three branches in Ruwi (Muscat), Sohar and Salalah.</p><p>Every job starts with a diagnosis and an estimate before any work, and you get updates on WhatsApp.</p>' },
  { title: 'Contact', slug: 'contact', column: 'company', kind: 'contact', body: '' },
  { title: 'Areas we cover', slug: 'areas', column: 'help', kind: 'areas', body: '' },
  { title: 'FAQ', slug: 'faq', column: 'help', kind: 'faq', body: '' },
  { title: 'Privacy policy', slug: 'privacy', column: 'policies', kind: 'text', body: '' },
  { title: 'Terms of service', slug: 'terms', column: 'policies', kind: 'text', body: '' },
] as const;
