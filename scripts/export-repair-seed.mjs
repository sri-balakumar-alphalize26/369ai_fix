// Writes odoo/369ai_fix/repair/data/seed_repairs.json from the site's
// own repair list (src/data/devices.ts, menu.ts, photos.ts) and copies the
// repair photos into the module. Run once after changing those files:
//   node scripts/export-repair-seed.mjs
// Only reads src/. The Odoo module loads the JSON on install, never on update,
// so prices and texts edited in Odoo are not overwritten.
import { build } from 'esbuild';
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const moduleDir = join(root, 'odoo', '369ai_fix');
const tmp = join(root, '.cache', 'repair-seed.mjs');

// Website category -> Odoo device.category name and product code prefix.
const ODOO = {
  mobile: ['Mobile Phone', 'MOB'],
  tablet: ['Tablet', 'TAB'],
  laptop: ['Laptop', 'LAP'],
  desktop: ['Desktop', 'DSK'],
  printer: ['Printer', 'PRN'],
  cctv: ['CCTV Installation', 'CCTV'],
  network: ['Networking & Wi-Fi', 'NET'],
  data: ['Data Recovery', 'DATA'],
  itsupport: ['IT Support', 'ITS'],
};
// Categories mobile_repair does not ship: their brands and models come from the site.
const NEW_CATEGORIES = new Set(['cctv', 'network', 'data', 'itsupport']);

const slug = (s) => s.toUpperCase().replace(/&/g, 'AND').replace(/[^A-Z0-9]+/g, '-').replace(/^-|-$/g, '');

await build({
  stdin: {
    contents: `
      export { categories } from './src/data/devices.ts';
      export { issueNotes } from './src/data/menu.ts';
      export { photo } from './src/data/photos.ts';`,
    resolveDir: root,
    loader: 'js',
  },
  bundle: true,
  format: 'esm',
  platform: 'node',
  outfile: tmp,
  logLevel: 'error',
});
const { categories, issueNotes, photo } = await import(pathToFileURL(tmp).href);

mkdirSync(join(moduleDir, 'repair', 'data'), { recursive: true });
mkdirSync(join(moduleDir, 'static', 'seed'), { recursive: true });

const out = categories.map((c) => {
  const [odooName, prefix] = ODOO[c.id];
  return {
    code: c.id,
    odoo_category: odooName,
    website_name: c.name,
    onsite_only: !!c.onsiteOnly,
    repairs: c.issues.map((issue, i) => {
      const pic = photo[`${c.id}:${issue}`];
      const file = pic ? `${pic}.jpg` : '';
      if (file) copyFileSync(join(root, 'public', 'media', 'repairs', file), join(moduleDir, 'static', 'seed', file));
      return {
        name: issue,
        default_code: `${prefix}-${slug(issue)}`,
        note: issueNotes[issue] || '',
        sequence: (i + 1) * 10,
        photo: file,
      };
    }),
    brands: NEW_CATEGORIES.has(c.id) ? c.brands.map((b) => ({ name: b.name, models: b.models })) : [],
  };
});

const target = join(moduleDir, 'repair', 'data', 'seed_repairs.json');
writeFileSync(target, JSON.stringify({ categories: out }, null, 1) + '\n');
const repairs = out.reduce((n, c) => n + c.repairs.length, 0);
const photos = out.reduce((n, c) => n + c.repairs.filter((r) => r.photo).length, 0);
console.log(`wrote ${target}: ${out.length} categories, ${repairs} repairs, ${photos} photos`);
if (!existsSync(target)) process.exit(1);
