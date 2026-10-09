// Site settings changed by the admin (server only). Stored in data/settings.json.
// Kept behind these two functions so it can move to a real database later
// without touching anything that uses it.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

export type Settings = {
  /** Admin: "Automatic Currency Conversion" — detect country by IP and convert prices. */
  autoCurrency: boolean;
};

const DEFAULTS: Settings = { autoCurrency: true };
const FILE = join(process.cwd(), 'data', 'settings.json');

let cached: { value: Settings; at: number } | null = null;

export async function getSettings(): Promise<Settings> {
  if (cached && Date.now() - cached.at < 5000) return cached.value; // re-read at most every 5 s
  let value = { ...DEFAULTS };
  try {
    const raw = JSON.parse(await readFile(FILE, 'utf8'));
    if (typeof raw?.autoCurrency === 'boolean') value.autoCurrency = raw.autoCurrency;
  } catch {
    /* no file yet → defaults */
  }
  cached = { value, at: Date.now() };
  return value;
}

export async function saveSettings(patch: Partial<Settings>): Promise<Settings> {
  const next = { ...(await getSettings()) };
  if (typeof patch.autoCurrency === 'boolean') next.autoCurrency = patch.autoCurrency; // only valid fields
  await mkdir(dirname(FILE), { recursive: true });
  await writeFile(FILE, JSON.stringify(next, null, 2) + '\n');
  cached = { value: next, at: Date.now() };
  return next;
}
