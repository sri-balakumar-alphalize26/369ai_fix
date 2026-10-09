// "What our clients say" on the Home page.
//
// ⚠ SAMPLE CONTENT. These are placeholders written to show the layout — they
// are not real customers. `sample: true` makes the section show a visible
// "Sample reviews" label. Replace them with real reviews (Google Maps →
// "Danat Computer Supermarket" → Reviews, or Facebook), copied word for word
// with the rating the customer actually gave, then set `sample` to false.

export const sample = true;

export interface Review {
  name: string;
  area: string;
  service: string;
  rating: 1 | 2 | 3 | 4 | 5;
  text: string;
}

export const reviews: Review[] = [
  { name: 'Sample customer', area: 'Al Khuwair', service: 'iPhone screen replacement', rating: 5, text: 'The technician came to my office and replaced the screen in about 40 minutes. Clear explanation before starting.' },
  { name: 'Sample customer', area: 'Qurum', service: 'Laptop battery', rating: 5, text: 'Booked in the morning, laptop was picked up and back the next day with a new battery. Easy process.' },
  { name: 'Sample customer', area: 'Sohar', service: 'CCTV installation', rating: 5, text: 'They surveyed the shop first, installed four cameras and set up viewing on my phone.' },
  { name: 'Sample customer', area: 'Ruwi', service: 'Printer repair', rating: 4, text: 'Office printer kept jamming. Fixed on-site and they showed us how to avoid it happening again.' },
  { name: 'Sample customer', area: 'Salalah', service: 'Data recovery', rating: 5, text: 'Recovered photos from a hard disk that would not show up on any computer.' },
  { name: 'Sample customer', area: 'Al Ghubrah', service: 'Wi-Fi setup', rating: 5, text: 'Weak signal upstairs is gone after the mesh setup. Tidy cabling too.' },
];
