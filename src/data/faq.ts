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
  // DRAFT (26 Oct 2026), written from what the site does; the owner to review. Odoo's Info Pages override it.
  { title: 'Privacy policy', slug: 'privacy', column: 'policies', kind: 'text',
    body: '<p>When you book a repair or sign in, we keep your name, mobile number, email (if you give one), the address and map pin for the visit, and the photos, video and notes you send about the device.</p><p>We use them only to arrange and carry out your repair: to confirm the booking, send the technician, keep you updated on WhatsApp and show your orders under My account. Your technician sees what the visit needs. We do not sell your details or use them for other companies\' advertising.</p><p>The site keeps you signed in with a cookie on your device, and keeps your cart in your browser. Signing out removes the sign-in.</p><p>To see, correct or delete what we hold about you, chat with us on WhatsApp or call us.</p>' },
  { title: 'Terms of service', slug: 'terms', column: 'policies', kind: 'text',
    body: '<p>Prices on the site are estimates. The technician checks your device first and confirms the final price with you before any work starts; nothing is repaired without your OK.</p><p>If the repair needs more work or a part, we may take the device to our lab and tell you how long it will take and what it costs before we go ahead.</p><p>Please back up your data before a repair where you can. We only access what the repair needs.</p><p>You can cancel or move a booking before the visit by chatting with us on WhatsApp.</p><p>Questions about a repair or a bill? Chat with us on WhatsApp or call us, and we will sort it out.</p>' },
] as const;
