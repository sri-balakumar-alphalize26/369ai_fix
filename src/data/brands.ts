// Every brand and model is listed by default (manager instruction).
// Add or remove models here; the catalog and booking form both read this.

export interface Brand {
  id: string;
  name: string;
  hue: number; // accent hue for the brand chip
  models: string[];
}

export const brands: Brand[] = [
  {
    id: 'apple',
    name: 'Apple',
    hue: 210,
    models: [
      'iPhone 17 Pro Max', 'iPhone 17 Pro', 'iPhone Air', 'iPhone 17',
      'iPhone 16 Pro Max', 'iPhone 16 Pro', 'iPhone 16 Plus', 'iPhone 16', 'iPhone 16e',
      'iPhone 15 Pro Max', 'iPhone 15 Pro', 'iPhone 15 Plus', 'iPhone 15',
      'iPhone 14 Pro Max', 'iPhone 14 Pro', 'iPhone 14 Plus', 'iPhone 14',
      'iPhone 13 Pro Max', 'iPhone 13 Pro', 'iPhone 13', 'iPhone 13 mini',
      'iPhone 12 Pro Max', 'iPhone 12 Pro', 'iPhone 12', 'iPhone 12 mini',
      'iPhone 11 Pro Max', 'iPhone 11 Pro', 'iPhone 11', 'iPhone SE (3rd gen)',
    ],
  },
  {
    id: 'samsung',
    name: 'Samsung',
    hue: 230,
    models: [
      'Galaxy S25 Ultra', 'Galaxy S25+', 'Galaxy S25', 'Galaxy S25 Edge', 'Galaxy S25 FE',
      'Galaxy S24 Ultra', 'Galaxy S24+', 'Galaxy S24', 'Galaxy S24 FE',
      'Galaxy S23 Ultra', 'Galaxy S23', 'Galaxy S23 FE',
      'Galaxy Z Fold7', 'Galaxy Z Flip7', 'Galaxy Z Fold6', 'Galaxy Z Flip6',
      'Galaxy A56', 'Galaxy A36', 'Galaxy A26', 'Galaxy A55', 'Galaxy A35', 'Galaxy A16',
      'Galaxy M55', 'Galaxy M35', 'Galaxy F55',
    ],
  },
  {
    id: 'google',
    name: 'Google Pixel',
    hue: 140,
    models: [
      'Pixel 10 Pro XL', 'Pixel 10 Pro', 'Pixel 10', 'Pixel 10 Pro Fold',
      'Pixel 9 Pro XL', 'Pixel 9 Pro', 'Pixel 9', 'Pixel 9a', 'Pixel 9 Pro Fold',
      'Pixel 8 Pro', 'Pixel 8', 'Pixel 8a', 'Pixel 7 Pro', 'Pixel 7', 'Pixel 7a',
    ],
  },
  {
    id: 'oneplus',
    name: 'OnePlus',
    hue: 0,
    models: [
      'OnePlus 13', 'OnePlus 13R', 'OnePlus 13s', 'OnePlus 12', 'OnePlus 12R',
      'OnePlus 11', 'OnePlus Open', 'Nord 5', 'Nord CE5', 'Nord 4', 'Nord CE4', 'Nord CE4 Lite',
    ],
  },
  {
    id: 'xiaomi',
    name: 'Xiaomi / Redmi',
    hue: 25,
    models: [
      'Xiaomi 15 Ultra', 'Xiaomi 15', 'Xiaomi 14 Ultra', 'Xiaomi 14', 'Xiaomi 14 Civi',
      'Redmi Note 14 Pro+', 'Redmi Note 14 Pro', 'Redmi Note 14', 'Redmi Note 13 Pro+',
      'Redmi Note 13', 'Redmi 14C', 'Redmi 13C', 'POCO F7', 'POCO X7 Pro', 'POCO M7 Pro',
    ],
  },
  {
    id: 'vivo',
    name: 'Vivo',
    hue: 220,
    models: [
      'X200 Pro', 'X200', 'X200 FE', 'X100 Pro', 'V50', 'V50e', 'V40 Pro', 'V40',
      'T4 Ultra', 'T4', 'T3 Ultra', 'Y400', 'Y300', 'Y58',
    ],
  },
  {
    id: 'oppo',
    name: 'OPPO',
    hue: 160,
    models: [
      'Find X8 Pro', 'Find X8', 'Find N5', 'Reno 14 Pro', 'Reno 14', 'Reno 13 Pro', 'Reno 13',
      'Reno 12 Pro', 'F29 Pro', 'F27 Pro+', 'K13', 'A5 Pro', 'A3 Pro',
    ],
  },
  {
    id: 'realme',
    name: 'realme',
    hue: 50,
    models: [
      'GT 7 Pro', 'GT 7', 'GT 6', '15 Pro', '15', '14 Pro+', '14 Pro', '14x',
      'Narzo 80 Pro', 'Narzo 70 Turbo', 'P3 Pro', 'P3x', 'C75', 'C65',
    ],
  },
  {
    id: 'iqoo',
    name: 'iQOO',
    hue: 280,
    models: ['iQOO 13', 'iQOO 12', 'iQOO Neo 10', 'iQOO Neo 10R', 'iQOO Z10', 'iQOO Z10x', 'iQOO Z9s Pro'],
  },
  {
    id: 'motorola',
    name: 'Motorola',
    hue: 195,
    models: [
      'Edge 60 Pro', 'Edge 60 Fusion', 'Edge 50 Ultra', 'Edge 50 Pro', 'Edge 50 Fusion',
      'Razr 60 Ultra', 'Razr 60', 'Razr 50', 'Moto G96', 'Moto G86', 'Moto G85', 'Moto G64',
    ],
  },
  {
    id: 'nothing',
    name: 'Nothing',
    hue: 0,
    models: ['Phone (3)', 'Phone (3a) Pro', 'Phone (3a)', 'Phone (2a) Plus', 'Phone (2a)', 'Phone (2)', 'CMF Phone 2 Pro', 'CMF Phone 1'],
  },
];

export const modelCount = brands.reduce((n, b) => n + b.models.length, 0);
