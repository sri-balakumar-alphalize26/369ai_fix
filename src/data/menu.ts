// Content for the Services mega menu (six switchable styles, see MegaMenu.astro).

// One-line captions for repairs, as in the menu mockups.
export const issueNotes: Record<string, string> = {
  'Screen replacement': 'Cracked or broken screen',
  'Battery replacement': 'Original batteries',
  'Charging port': 'Fix charging issues',
  'Back glass': 'Cracked back panel',
  Camera: 'Front & rear camera',
  'Speaker / microphone': 'No sound or muffled audio',
  'Water damage': 'Cleaning & recovery',
  'Software & data': 'OS update and troubleshooting',
  'Screen / glass': 'Cracked glass or display',
  Buttons: 'Power and volume keys',
  'Display / touch not working': 'Lines, dead pixels, no touch',
  'Keyboard / trackpad': 'Keys, backlight, trackpad',
  'Hinge repair': 'Loose or broken hinges',
  'Not powering on': 'No power, no display',
  'Power supply': 'Dead or faulty PSU',
  'Graphics card': 'No display, artefacts, upgrades',
  'Custom PC build': 'Gaming, office or workstation',
  'Motherboard repair': 'Board-level repair',
  'SSD / RAM upgrade': 'Faster, more storage',
  'OS install & virus removal': 'Clean install, malware removal',
  'Overheating / fan': 'Cleaning and fan replacement',
  'Paper jam': 'Clear and fix feed rollers',
  'Poor print quality': 'Streaks, fading, smudges',
  'New CCTV installation': 'Survey and full install',
  'DVR / NVR setup': 'Recording and storage',
  'Mobile remote viewing': 'Watch cameras on your phone',
  'Wi-Fi setup': 'Router and mesh setup',
  'Weak Wi-Fi / dead zones': 'Coverage survey and fix',
  'Deleted files': 'Recover lost files',
  'Drive not detected': 'Dead or failing drives',
};
export const note = (issue: string) => issueNotes[issue] ?? 'Diagnosed first, estimate before work';

// Brand badge colours (text badges — no trademark logo files are used).
export const brandColor: Record<string, string> = {
  Apple: '#111111', Samsung: '#1428a0', 'Google Pixel': '#4285f4', OnePlus: '#eb0028', 'Xiaomi / Redmi': '#ff6900',
  Vivo: '#415fff', OPPO: '#1ba784', realme: '#ffc915', iQOO: '#7b3fe4', Motorola: '#5c92fa', Nothing: '#111111',
};

export const quickLinks = [
  { label: 'Book a Repair', href: '/services#catalog' },
  { label: 'Check Coverage', href: '/services#modes' },
  { label: 'Doorstep Service', href: '/services?mode=doorstep#modes' },
  { label: 'Pickup & Service', href: '/services?mode=pickup#modes' },
  { label: 'Repair Catalog', href: '/services#catalog' },
  { label: 'FAQ', href: '/services#faq' },
  { label: 'Our Team', href: '/team' },
];

// Which illustration each category uses (DeviceArt kinds).
export const artFor: Record<string, string> = {
  mobile: 'phone', tablet: 'tablet', laptop: 'laptop', desktop: 'desktop', printer: 'printer',
  cctv: 'cctv', network: 'router', data: 'drive', itsupport: 'support',
};
