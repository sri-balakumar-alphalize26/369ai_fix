// Every device category we service, with all brands and models listed by
// default (manager instruction). Phones live in brands.ts; the rest are here.
// `onsiteOnly` categories (CCTV, networking) are installed at the customer's
// place, so they cannot be booked as pickup.
import { brands as phoneBrands, type Brand } from './brands';

export type Icon = 'phone' | 'tablet' | 'laptop' | 'desktop' | 'printer' | 'cctv' | 'network' | 'drive' | 'support';

export interface Category {
  id: string;
  name: string;
  short: string;
  icon: Icon;
  hue: number;
  onsiteOnly?: boolean;
  issues: string[];
  brands: Brand[];
}

export const categories: Category[] = [
  {
    id: 'mobile',
    name: 'Mobile Phones',
    short: 'Screens, batteries, ports and board repair',
    icon: 'phone',
    hue: 265,
    issues: ['Screen replacement', 'Battery replacement', 'Charging port', 'Back glass', 'Camera', 'Speaker / microphone', 'Water damage', 'Software & data'],
    brands: phoneBrands,
  },
  {
    id: 'tablet',
    name: 'Tablets & iPads',
    short: 'Glass, batteries and charging faults',
    icon: 'tablet',
    hue: 200,
    issues: ['Screen / glass', 'Display / touch not working', 'Battery replacement', 'Charging port', 'Buttons', 'Software & data'],
    brands: [
      { id: 'ipad', name: 'Apple iPad', hue: 210, models: ['iPad Pro 13" (M4)', 'iPad Pro 11" (M4)', 'iPad Air 13" (M3)', 'iPad Air 11" (M3)', 'iPad (A16)', 'iPad 10th gen', 'iPad 9th gen', 'iPad mini (A17 Pro)', 'iPad mini 6'] },
      { id: 'galaxy-tab', name: 'Samsung Galaxy Tab', hue: 230, models: ['Galaxy Tab S10 Ultra', 'Galaxy Tab S10+', 'Galaxy Tab S9 FE', 'Galaxy Tab S9', 'Galaxy Tab A9+', 'Galaxy Tab A9'] },
      { id: 'other-tab', name: 'Lenovo / Xiaomi / OnePlus', hue: 20, models: ['Lenovo Tab P12', 'Lenovo Tab M11', 'Xiaomi Pad 7', 'Redmi Pad Pro', 'Redmi Pad SE', 'OnePlus Pad 2', 'OnePlus Pad Go'] },
    ],
  },
  {
    id: 'laptop',
    name: 'Laptops & MacBooks',
    short: 'Screens, keyboards, hinges, motherboards',
    icon: 'laptop',
    hue: 220,
    issues: ['Screen replacement', 'Keyboard / trackpad', 'Battery replacement', 'Hinge repair', 'Not powering on', 'Motherboard repair', 'SSD / RAM upgrade', 'OS install & virus removal', 'Overheating / fan'],
    brands: [
      { id: 'macbook', name: 'Apple MacBook', hue: 210, models: ['MacBook Air 13" (M4)', 'MacBook Air 15" (M4)', 'MacBook Air (M3)', 'MacBook Air (M2)', 'MacBook Air (M1)', 'MacBook Pro 14" (M4)', 'MacBook Pro 16" (M4)', 'MacBook Pro 14" (M3)', 'MacBook Pro 13" (M2)', 'MacBook Pro (Intel)'] },
      { id: 'dell', name: 'Dell', hue: 205, models: ['XPS 13', 'XPS 14', 'XPS 16', 'Inspiron 14', 'Inspiron 15', 'Inspiron 16', 'Vostro 14', 'Vostro 15', 'Latitude 5000 series', 'Latitude 7000 series', 'Alienware m16'] },
      { id: 'hp', name: 'HP', hue: 200, models: ['Spectre x360', 'Envy x360', 'Pavilion 14', 'Pavilion 15', 'Victus 15', 'Omen 16', 'HP 15s', 'EliteBook 840', 'ProBook 450'] },
      { id: 'lenovo', name: 'Lenovo', hue: 0, models: ['ThinkPad X1 Carbon', 'ThinkPad T14', 'ThinkPad E14', 'ThinkBook 14', 'ThinkBook 15', 'IdeaPad Slim 3', 'IdeaPad Slim 5', 'Yoga Slim 7', 'Legion 5', 'LOQ 15'] },
      { id: 'asus', name: 'ASUS', hue: 250, models: ['Zenbook 14 OLED', 'Vivobook 15', 'Vivobook 16', 'ROG Strix G16', 'ROG Zephyrus G14', 'TUF Gaming A15', 'ExpertBook B1'] },
      { id: 'acer', name: 'Acer', hue: 140, models: ['Swift Go 14', 'Aspire 5', 'Aspire 7', 'Aspire Lite', 'Nitro V 15', 'Predator Helios Neo 16', 'TravelMate P2'] },
      { id: 'msi', name: 'MSI', hue: 355, models: ['Modern 14', 'Modern 15', 'Thin GF63', 'Katana 15', 'Cyborg 15', 'Prestige 14'] },
    ],
  },
  {
    id: 'desktop',
    name: 'Desktops & All-in-ones',
    short: 'Office PCs, iMacs, gaming builds',
    icon: 'desktop',
    hue: 180,
    issues: ['Not powering on', 'Power supply', 'Motherboard repair', 'SSD / RAM upgrade', 'Graphics card', 'OS install & virus removal', 'Custom PC build'],
    brands: [
      { id: 'imac', name: 'Apple iMac / Mac mini', hue: 210, models: ['iMac 24" (M4)', 'iMac 24" (M3)', 'iMac 24" (M1)', 'iMac 27" (Intel)', 'Mac mini (M4)', 'Mac mini (M2)', 'Mac Studio'] },
      { id: 'dell-pc', name: 'Dell', hue: 205, models: ['OptiPlex Micro', 'OptiPlex Tower', 'Inspiron Desktop', 'Inspiron 24 AIO', 'Vostro Desktop'] },
      { id: 'hp-pc', name: 'HP', hue: 200, models: ['ProDesk 400', 'EliteDesk 800', 'Pavilion Desktop', 'HP All-in-One 24', 'Victus 15L'] },
      { id: 'lenovo-pc', name: 'Lenovo', hue: 0, models: ['ThinkCentre M70', 'ThinkCentre Neo 50', 'IdeaCentre AIO 3', 'IdeaCentre Tower', 'Legion Tower 5'] },
      { id: 'custom', name: 'Custom & assembled PCs', hue: 280, models: ['Gaming PC', 'Office PC', 'Workstation', 'Server tower'] },
    ],
  },
  {
    id: 'printer',
    name: 'Printers',
    short: 'Laser, inkjet, thermal and barcode',
    icon: 'printer',
    hue: 30,
    issues: ['Paper jam', 'Poor print quality', 'Head cleaning / alignment', 'Toner / cartridge issue', 'Not connecting (Wi-Fi / USB)', 'Error codes', 'Roller & fuser replacement', 'Setup & installation'],
    brands: [
      { id: 'hp-print', name: 'HP', hue: 200, models: ['LaserJet Pro M111', 'LaserJet Pro MFP M135', 'LaserJet MFP M141', 'LaserJet Pro 4003', 'Smart Tank 580', 'Smart Tank 670', 'DeskJet 2331', 'OfficeJet Pro 9120'] },
      { id: 'canon', name: 'Canon', hue: 0, models: ['PIXMA G3010', 'PIXMA G3020', 'PIXMA G570', 'PIXMA E477', 'imageCLASS LBP6030', 'imageCLASS MF3010', 'imageCLASS MF244dw', 'imageRUNNER 2206'] },
      { id: 'epson', name: 'Epson', hue: 215, models: ['EcoTank L3250', 'EcoTank L3252', 'EcoTank L4260', 'EcoTank L6270', 'EcoTank L8050', 'WorkForce WF-2930', 'LQ-310 (dot matrix)'] },
      { id: 'brother', name: 'Brother', hue: 225, models: ['HL-L2321D', 'HL-L2351DW', 'DCP-L2541DW', 'MFC-L2701DW', 'DCP-T420W', 'DCP-T820DW'] },
      { id: 'thermal', name: 'Thermal & barcode', hue: 40, models: ['TVS RP 3160', 'Epson TM-T82', 'Zebra ZD220', 'Zebra GC420t', 'TSC TTP-244 Pro', 'Honeywell PC42t'] },
      { id: 'office', name: 'Office copiers', hue: 160, models: ['Kyocera ECOSYS', 'Ricoh MP series', 'Konica Minolta bizhub', 'Xerox VersaLink', 'Sharp AR series'] },
    ],
  },
  {
    id: 'cctv',
    name: 'CCTV Installation',
    short: 'Survey, install and maintain cameras',
    icon: 'cctv',
    hue: 340,
    onsiteOnly: true,
    issues: ['New CCTV installation', 'Add more cameras', 'DVR / NVR setup', 'Mobile remote viewing', 'Camera not showing', 'Recording / hard disk issue', 'Cabling & re-wiring', 'Annual maintenance'],
    brands: [
      { id: 'hikvision', name: 'Hikvision', hue: 0, models: ['2MP Dome camera', '2MP Bullet camera', '4MP IP camera', 'ColorVu night camera', 'PTZ camera', 'DVR (4 / 8 / 16 ch)', 'NVR (4 / 8 / 16 ch)'] },
      { id: 'dahua', name: 'Dahua', hue: 15, models: ['HDCVI Dome camera', 'HDCVI Bullet camera', 'IP camera 4MP', 'Full-color camera', 'XVR recorder', 'NVR recorder'] },
      { id: 'cpplus', name: 'CP Plus', hue: 210, models: ['Dome camera', 'Bullet camera', 'Wi-Fi camera (EZYKAM)', 'IP camera', 'DVR', 'NVR'] },
      { id: 'wifi-cam', name: 'Home Wi-Fi cameras', hue: 150, models: ['TP-Link Tapo C200', 'TP-Link Tapo C320WS', 'Imou Ranger 2', 'Mi 360° Home Camera', 'Qubo Home Cam', 'Video doorbell'] },
    ],
  },
  {
    id: 'network',
    name: 'Networking & Wi-Fi',
    short: 'Routers, cabling, Wi-Fi coverage',
    icon: 'network',
    hue: 160,
    onsiteOnly: true,
    issues: ['Wi-Fi setup', 'Weak Wi-Fi / dead zones', 'Mesh Wi-Fi install', 'LAN cabling', 'Router / firewall config', 'Switch & rack setup', 'Office network'],
    brands: [
      { id: 'tplink', name: 'TP-Link', hue: 170, models: ['Archer router', 'Deco mesh', 'Omada access point', 'Managed switch'] },
      { id: 'ubiquiti', name: 'Ubiquiti', hue: 210, models: ['UniFi access point', 'UniFi Dream Machine', 'UniFi switch'] },
      { id: 'cisco', name: 'Cisco', hue: 195, models: ['Catalyst switch', 'Meraki access point', 'Small business router'] },
      { id: 'dlink', name: 'D-Link / Netgear', hue: 30, models: ['D-Link router', 'D-Link switch', 'Netgear Orbi mesh', 'Netgear Nighthawk'] },
    ],
  },
  {
    id: 'data',
    name: 'Data Recovery',
    short: 'Drives, SSDs, memory cards, phones',
    icon: 'drive',
    hue: 45,
    issues: ['Deleted files', 'Drive not detected', 'Clicking / dead hard disk', 'Formatted drive', 'Water / fire damage', 'Phone data recovery'],
    brands: [
      { id: 'hdd', name: 'Hard disks', hue: 45, models: ['Laptop HDD (2.5")', 'Desktop HDD (3.5")', 'External HDD (WD / Seagate)', 'NAS / RAID'] },
      { id: 'ssd', name: 'SSDs', hue: 200, models: ['SATA SSD', 'NVMe SSD', 'MacBook soldered SSD', 'External SSD (Samsung T7 / SanDisk)'] },
      { id: 'flash', name: 'Flash & cards', hue: 300, models: ['USB pen drive', 'SD / microSD card', 'CCTV hard disk'] },
    ],
  },
];

categories.push({
  id: 'itsupport',
  name: 'IT Support',
  short: 'Software, setup and troubleshooting',
  icon: 'support',
  hue: 205,
  onsiteOnly: true,
  issues: ['Software installation', 'Email & Microsoft 365 setup', 'Slow computer tune-up', 'Virus & malware removal', 'Printer & network setup', 'Annual maintenance contract'],
  brands: [
    { id: 'windows', name: 'Windows PCs', hue: 205, models: ['Windows 11', 'Windows 10', 'Windows Server'] },
    { id: 'macos', name: 'Apple macOS', hue: 210, models: ['macOS Sequoia', 'macOS Sonoma', 'macOS Ventura'] },
    { id: 'office', name: 'Office & email', hue: 20, models: ['Microsoft 365', 'Google Workspace', 'Outlook / Exchange'] },
  ],
});

export const totals = {
  categories: categories.length,
  brands: categories.reduce((n, c) => n + c.brands.length, 0),
  models: categories.reduce((n, c) => n + c.brands.reduce((m, b) => m + b.models.length, 0), 0),
};

// Line icons, 24x24, stroke="currentColor".
export const iconPaths: Record<Icon, string> = {
  phone: '<rect x="6" y="2.5" width="12" height="19" rx="2.5"/><path d="M10.5 18.5h3"/>',
  tablet: '<rect x="3.5" y="3" width="17" height="18" rx="2.5"/><path d="M11 18h2"/>',
  laptop: '<rect x="4" y="4.5" width="16" height="11" rx="1.5"/><path d="M2 19.5h20"/>',
  desktop: '<rect x="2.5" y="3.5" width="19" height="13" rx="1.5"/><path d="M8.5 21h7M12 16.5V21"/>',
  printer: '<path d="M7 9V3.5h10V9"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v6.5H7z"/>',
  cctv: '<path d="M3 7.5l13-3.5 2 5.5-13 3.5z"/><path d="M16.5 9l3.5 1.5-1 2.5-3.5-1M7 11.5L6 15H3M3 12.5V18"/>',
  network: '<path d="M2 9a15 15 0 0 1 20 0M5.5 12.5a10 10 0 0 1 13 0M9 16a5 5 0 0 1 6 0"/><circle cx="12" cy="19.5" r="1"/>',
  drive: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3 14h18"/><circle cx="17" cy="16.5" r=".8"/>',
  support: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
