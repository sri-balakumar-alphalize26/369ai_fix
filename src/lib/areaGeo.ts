// APPROXIMATE centre points for the coverage areas (town/district level), used only to
// find the nearest one to a visitor. Not addresses. Shared by the Home location check
// and the booking wizard's "Use my location".
export const areaGeo: Record<string, [number, number]> = {
  Ruwi: [23.593, 58.545], Muttrah: [23.617, 58.567], 'Wadi Kabir': [23.573, 58.578], Darsait: [23.607, 58.555],
  'Al Wattayah': [23.595, 58.498], Qurum: [23.605, 58.478], 'Al Khuwair': [23.593, 58.426], 'Madinat Sultan Qaboos': [23.588, 58.448],
  'Al Ghubrah': [23.585, 58.395], Bausher: [23.555, 58.395], 'Al Azaiba': [23.583, 58.362], 'Al Hail': [23.645, 58.285],
  'Al Mawaleh': [23.628, 58.25], 'Al Khoudh': [23.61, 58.18], Seeb: [23.67, 58.19], Mabellah: [23.63, 58.13],
  'Al Amerat': [23.52, 58.49], Qurayyat: [23.26, 58.92],
  Sohar: [24.347, 56.709], 'Falaj Al Qabail': [24.4, 56.63], 'Al Hambar': [24.33, 56.73], Liwa: [24.53, 56.57],
  Shinas: [24.74, 56.47], Saham: [24.17, 56.89], 'Al Khaburah': [23.97, 57.1], Barka: [23.68, 57.89], 'Al Suwaiq': [23.85, 57.44],
  Salalah: [17.019, 54.089], 'Al Saada': [17.05, 54.13], 'Al Dahariz': [17.03, 54.14], Awqad: [17.03, 54.06],
  Taqah: [17.04, 54.4], Mirbat: [16.99, 54.69], Raysut: [16.95, 53.99],
};

export const branchGeo: { name: string; at: [number, number] }[] = [
  { name: 'Ruwi (Muscat)', at: [23.593, 58.556] },
  { name: 'Sohar', at: [24.347, 56.709] },
  { name: 'Salalah', at: [17.019, 54.089] },
];

/** Distance in km between two [lat, lng] points. */
export const km = (a: [number, number], b: [number, number]) => {
  const R = 6371, r = Math.PI / 180;
  const dLat = (b[0] - a[0]) * r, dLng = (b[1] - a[1]) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};
