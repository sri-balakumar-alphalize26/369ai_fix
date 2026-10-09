// SAMPLE profiles — placeholder names until real staff details and photos arrive.

export interface Member {
  name: string;
  role: string;
  skills: string[];
  hue: number;
}

export const teams: { id: string; title: string; blurb: string; members: Member[] }[] = [
  {
    id: 'technicians',
    title: 'Repair Technicians',
    blurb: 'Phones, laptops and desktops — board-level repair, on-site or in the lab.',
    members: [
      { name: 'Arjun Rao', role: 'Lead Technician', skills: ['Micro-soldering', 'iPhone', 'Face ID'], hue: 265 },
      { name: 'Meera Nair', role: 'Senior Technician', skills: ['Samsung', 'Foldables', 'OLED'], hue: 190 },
      { name: 'Rahul Verma', role: 'Doorstep Technician', skills: ['Screens', 'Batteries', 'Ports'], hue: 320 },
      { name: 'Sneha Iyer', role: 'Laptop Technician', skills: ['MacBook', 'ThinkPad', 'Hinges'], hue: 150 },
      { name: 'Farhan Sheikh', role: 'Lab Technician', skills: ['Water damage', 'Data recovery'], hue: 30 },
      { name: 'Divya Menon', role: 'Quality Check', skills: ['Testing', 'Calibration'], hue: 210 },
    ],
  },
  {
    id: 'field',
    title: 'Printer, CCTV & Network Engineers',
    blurb: 'On-site installation and servicing for homes, shops and offices.',
    members: [
      { name: 'Suresh Pillai', role: 'Printer Engineer', skills: ['Laser', 'Ink tank', 'Thermal'], hue: 30 },
      { name: 'Naveen Joseph', role: 'CCTV Installer', skills: ['Hikvision', 'Dahua', 'NVR setup'], hue: 340 },
      { name: 'Asif Ali', role: 'CCTV Installer', skills: ['Cabling', 'Remote viewing'], hue: 0 },
      { name: 'Deepak Shetty', role: 'Network Engineer', skills: ['Wi-Fi mesh', 'LAN', 'Firewalls'], hue: 165 },
    ],
  },
  {
    id: 'logistics',
    title: 'Pickup & Delivery',
    blurb: 'Riders who collect and return devices in sealed pouches.',
    members: [
      { name: 'Karthik S', role: 'Logistics Lead', skills: ['Routing', 'Scheduling'], hue: 45 },
      { name: 'Imran Khan', role: 'Pickup Rider', skills: ['East zone'], hue: 175 },
      { name: 'Vikram Gowda', role: 'Pickup Rider', skills: ['South zone'], hue: 290 },
      { name: 'Ravi Kumar', role: 'Pickup Rider', skills: ['North & West'], hue: 120 },
    ],
  },
  {
    id: 'support',
    title: 'Customer Support',
    blurb: 'The people who answer, book and track every repair.',
    members: [
      { name: 'Ananya Das', role: 'Support Lead', skills: ['Bookings', 'Escalations'], hue: 340 },
      { name: 'Pooja Reddy', role: 'Booking Coordinator', skills: ['Slots', 'Updates'], hue: 200 },
    ],
  },
];
