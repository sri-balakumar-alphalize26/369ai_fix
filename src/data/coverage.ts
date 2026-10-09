// SAMPLE coverage areas around Danat's three branches — the branch cities are
// real (Ruwi/Muscat, Sohar, Salalah); the area lists are not confirmed by the
// client. Doorstep is the tighter zone (a technician on the road); pickup
// covers the wider ring.
import type { ServiceModeId } from './site';

export interface Zone {
  name: string;
  areas: string[];
}

export const coverage: Record<ServiceModeId, { eta: string; zones: Zone[] }> = {
  doorstep: {
    eta: 'Technician at your door in about 60 minutes',
    zones: [
      { name: 'Muscat (Ruwi branch)', areas: ['Ruwi', 'Muttrah', 'Wadi Kabir', 'Darsait', 'Al Wattayah', 'Qurum', 'Al Khuwair', 'Madinat Sultan Qaboos', 'Al Ghubrah', 'Bausher', 'Al Azaiba'] },
      { name: 'Sohar', areas: ['Sohar', 'Falaj Al Qabail', 'Al Hambar'] },
      { name: 'Salalah', areas: ['Salalah', 'Al Saada', 'Al Dahariz', 'Awqad'] },
    ],
  },
  pickup: {
    eta: 'Picked up same day, back in 24–48 hours',
    zones: [
      { name: 'Muscat (Ruwi branch)', areas: ['Ruwi', 'Muttrah', 'Wadi Kabir', 'Darsait', 'Al Wattayah', 'Qurum', 'Al Khuwair', 'Madinat Sultan Qaboos', 'Al Ghubrah', 'Bausher', 'Al Azaiba', 'Al Hail', 'Al Mawaleh', 'Al Khoudh', 'Seeb', 'Mabellah', 'Al Amerat', 'Qurayyat'] },
      { name: 'Al Batinah (Sohar branch)', areas: ['Sohar', 'Falaj Al Qabail', 'Al Hambar', 'Liwa', 'Shinas', 'Saham', 'Al Khaburah', 'Barka', 'Al Suwaiq'] },
      { name: 'Dhofar (Salalah branch)', areas: ['Salalah', 'Al Saada', 'Al Dahariz', 'Awqad', 'Taqah', 'Mirbat', 'Raysut'] },
    ],
  },
};
