// The pop-ups, the Spin & Win wheel, the chat assistant and the "Book your slot" slider as they
// are in code: what shows when Odoo has never answered (Fix Website ▸ Pop-ups & chat edits them).
// `{site}` is the website's name, `{fee}` the visit-fee line and `{price}` the visit fee amount —
// filled on the server (src/lib/content.ts fill()). `{code}`, `{device}`, `{issue}`, `{area}`,
// `{slide}`, `{contact}`, `{method}`, `{branches}`, `{phone}`, `{email}`, `{hours}`, `{doorstep}`
// and `{pickup}` are filled by the component or in the browser.
import type { Popups, Wheel, Bot, Engage } from '../lib/content';

export const STATIC_POPUPS: Popups = {
  ann: { show: true, text: 'Doorstep repair across Oman — free diagnosis this week', button: 'Book now →', link: '/services#catalog', speed_s: 30 },
  welcome: { type: 'slot', delay_ms: 1500, flash_delay_ms: 4000, snooze_days: 30 },
  flash: {
    badge: 'Flash offer', title: 'Free diagnosis this week',
    body: 'Book a doorstep visit and the check-up is on us. {fee}.',
    code: '369FIX', button: 'Book with offer', button_link: '/services#catalog',
    wa_button: 'WhatsApp us', wa_msg: "Hello {site} — I'd like to use code {code}", later: 'No thanks',
  },
  cookie: {
    show: true, title: 'We use cookies',
    text: 'Only to remember your theme, area and choices on this site. No ads, no tracking.',
    decline: 'Decline', accept: 'Accept', delay_ms: 1200,
  },
};

export const STATIC_WHEEL: Wheel = {
  tab: 'Spin & Win', eyebrow: '✦ {site} rewards ✦', title: 'Spin &', title2: 'Win',
  subtitle: 'Every slice is a free extra on your next repair.',
  spin: 'Spin the wheel', later: 'Maybe later', won: '🎉 You won',
  note: 'Show this code when you book. Valid on your next repair.',
  book: 'Book now', wa: 'WhatsApp us', wa_msg: 'Hello {site} — I won on the spin wheel, code: {code}',
  slices: [
    { top: 'Free', label: 'Diagnosis', full: 'Free diagnosis', code: 'SPIN-DIAG', icon: 'diag', color: 'var(--violet)', text_color: '#fff' },
    { top: 'Free', label: 'Pickup', full: 'Free pickup & drop', code: 'SPIN-PICK', icon: 'pick', color: '#f5b400', text_color: '#10241a' },
    { top: 'Free', label: 'Cleaning', full: 'Free device cleaning', code: 'SPIN-CLEAN', icon: 'clean', color: '#16241d', text_color: '#fff' },
    { top: 'Priority', label: 'Slot', full: 'Priority same-day slot', code: 'SPIN-FAST', icon: 'fast', color: '#ff7a45', text_color: '#fff' },
    { top: 'Free', label: 'Backup', full: 'Free data backup', code: 'SPIN-DATA', icon: 'data', color: 'color-mix(in srgb, var(--violet) 55%, #fff)', text_color: '#10241a' },
    { top: 'Free', label: 'Guard', full: 'Free screen guard', code: 'SPIN-GUARD', icon: 'guard', color: '#fff', text_color: '#10241a' },
  ],
};

export const STATIC_BOT: Bot = {
  name: '{site} Assistant', status: 'Automated help · replies instantly',
  greeting: "Hi 👋 I'm the {site} assistant. I can help you book a repair, check your area or find a branch.",
  placeholder: 'Ask about a repair, area or price…', tip: 'Ask us anything', wa_tip: 'WhatsApp us',
  wa_msg: 'Hello {site} — I need help with a repair.',
  replies: [
    { label: '🔧 Book a repair', intent: 'book' }, { label: '📍 Do you cover my area?', intent: 'area' },
    { label: '💰 Prices', intent: 'price' }, { label: '⏱ How long?', intent: 'time' },
    { label: '🏢 Branches & contact', intent: 'contact' }, { label: '👤 Talk to a person', intent: 'human' },
  ],
  answers: {
    book: 'Great! Which device needs fixing?',
    dev: "What's the problem with your <b>{device}</b>?",
    iss: 'Got it — <b>{issue}</b> for {device}. {price} Tap below and your booking message is ready to send.',
    area: "Type your area name below (for example <i>Qurum</i> or <i>Sohar</i>) and I'll check.",
    price: 'Each repair shows its price on the site. Where none is shown, the technician gives you the price after checking the device — always before any work starts.<br>{fee}.',
    time: '<b>At your door:</b> {doorstep}.<br><b>If it goes to our lab:</b> {pickup}.',
    contact: 'We have branches in <b>{branches}</b>.<br>📞 {phone}<br>✉️ {email}',
    hours: 'Our opening hours: <b>{hours}</b>.',
    human: 'Sure — our team replies on WhatsApp.',
    menu: 'How else can I help?',
    found: '✅ Yes, we cover <b>{area}</b>. Want to book a repair there?',
    fallback: "I'm not sure about that one — our team can help on WhatsApp.",
  },
};

export const GENERIC_PERKS = ['Expert technicians', 'Price confirmed first', 'At your door', 'Updates on WhatsApp'];

export const STATIC_ENGAGE: Engage = {
  eyebrow: 'Book your slot', title2_generic: 'repair at your door', perks_generic: [...GENERIC_PERKS], from_label: 'Starting from',
  slide_ms: 3500, idle_s: 35, still_s: 15,
  wa_msg: 'Hi {site}, I want to book {slide}. My contact: {contact}',
  form: {
    pill: 'Book instantly on WhatsApp', title: 'Book your slot',
    subtitle: "Share your number or email and we'll start the booking on WhatsApp.",
    privacy: 'No spam. We only use your {method} to confirm the booking.',
    send: 'Send on WhatsApp', all: 'View all services', all_link: '/services#all',
    features: [{ title: 'Quick Service', small: 'In most areas' }, { title: 'Genuine Parts', small: 'Trusted quality' }, { title: 'Best Price', small: 'Transparent pricing' }],
  },
  // keyed by the site's own category id (`cat`); Odoo rows carry `category_id` instead
  slides: [
    { category_id: null, cat: 'mobile', category: 'Mobile Phone', title: 'Mobile', title2: 'Repair',
      pitch: 'Screen, battery, charging, camera and more – quick and reliable service.',
      perks: ['Genuine parts', 'Expert technicians', 'Affordable pricing', 'Quick turnaround'] },
    { category_id: null, cat: 'laptop', category: 'Laptop', title: 'Laptop', title2: 'Repair',
      pitch: 'Screens, keyboards, batteries, hinges and board-level repair.',
      perks: ['Genuine parts', 'Board-level repair', 'Affordable pricing', 'Pickup & drop'] },
    { category_id: null, cat: 'printer', category: 'Printer', title: 'Printer', title2: 'Repair',
      pitch: 'Paper jams, print quality, toner and setup – fixed on-site.',
      perks: ['On-site service', 'All major brands', 'Affordable pricing', 'Setup included'] },
    { category_id: null, cat: 'cctv', category: 'CCTV Installation', title: 'CCTV', title2: 'Installation',
      pitch: 'Site survey, camera install, DVR/NVR setup and phone viewing.',
      perks: ['Site survey first', 'Clean cabling', 'Remote viewing', 'Maintenance plans'] },
    { category_id: null, cat: 'data', category: 'Data Recovery', title: 'Data', title2: 'Recovery',
      pitch: 'Deleted files, dead drives and formatted disks recovered.',
      perks: ['Honest assessment', 'Secure handling', 'All drive types', 'Updates on WhatsApp'] },
  ],
  exit: {
    title: 'Leaving already? 👋', status: 'We reply on WhatsApp',
    text: "What do you need fixed today? Tap one — we'll reply on WhatsApp.",
    button: 'Chat with us on WhatsApp', wa_msg: 'Hi {site}, I need help with a repair.',
    tile_msg: 'Hi {site}, I need help with my {device}.', link: '/#book-services', link_label: 'See all services →',
    // every device type except tablets, desktops and IT support (label '' = the category's short name)
    tiles: ['mobile', 'laptop', 'printer', 'cctv', 'network', 'data'].map((cat) => ({ category_id: null, cat, category: '', label: '' })),
  },
};
