// Live exchange rates, fetched on the server and cached.
// Provider: open.er-api.com (free, no key). If FX_API_KEY is set, the keyed
// exchangerate-api.com v6 endpoint is used instead (key never leaves the server).
// Cache: memory + .cache/rates-<BASE>.json for 6 h. On provider failure the last good
// rates are served; with no good rates at all the caller gets null (→ show base currency).
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const TTL = 6 * 3600 * 1000;
const CACHE_DIR = join(process.cwd(), '.cache');

export type Rates = { base: string; rates: Record<string, number>; fetchedAt: number; source: string };

const mem = new Map<string, Rates>();
const inflight = new Map<string, Promise<Rates | null>>();

function providerUrl(base: string): string {
  const custom = process.env.FX_API_URL; // used by tests to simulate an outage
  if (custom) return custom.replace('{BASE}', base);
  const key = process.env.FX_API_KEY;
  return key
    ? `https://v6.exchangerate-api.com/v6/${encodeURIComponent(key)}/latest/${base}`
    : `https://open.er-api.com/v6/latest/${base}`;
}

/** Accept only a sane payload: an object of finite positive numbers that includes the base. */
export function validateRates(base: string, raw: unknown): Record<string, number> | null {
  if (!raw || typeof raw !== 'object') return null;
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (/^[A-Z]{3}$/.test(k) && typeof v === 'number' && Number.isFinite(v) && v > 0) out[k] = v;
  }
  if (Math.abs((out[base] ?? 0) - 1) > 1e-9) return null; // base must be 1
  return Object.keys(out).length > 10 ? out : null;
}

async function readDisk(base: string): Promise<Rates | null> {
  try {
    const r = JSON.parse(await readFile(join(CACHE_DIR, `rates-${base}.json`), 'utf8')) as Rates;
    return validateRates(base, r.rates) ? r : null;
  } catch {
    return null;
  }
}

async function writeDisk(r: Rates) {
  try {
    await mkdir(CACHE_DIR, { recursive: true });
    await writeFile(join(CACHE_DIR, `rates-${r.base}.json`), JSON.stringify(r));
  } catch {
    /* disk cache is optional */
  }
}

async function fetchRates(base: string): Promise<Rates | null> {
  const r = await fetch(providerUrl(base), { signal: AbortSignal.timeout(5000), headers: { accept: 'application/json' } });
  if (!r.ok) throw new Error(`rates HTTP ${r.status}`);
  const j: any = await r.json();
  const rates = validateRates(base, j?.rates ?? j?.conversion_rates);
  if (!rates) throw new Error('rates payload invalid');
  return { base, rates, fetchedAt: Date.now(), source: new URL(providerUrl(base)).host };
}

/** Rates for `base` (fresh ≤ 6 h, else refreshed). Returns last good rates on failure, or null. */
export async function getRates(base: string): Promise<Rates | null> {
  base = base.toUpperCase();
  let cur = mem.get(base) ?? (await readDisk(base));
  if (cur) mem.set(base, cur);
  if (cur && Date.now() - cur.fetchedAt < TTL) return cur;

  // one network request shared by everyone asking at the same moment
  if (!inflight.has(base)) {
    inflight.set(
      base,
      fetchRates(base)
        .then(async (fresh) => {
          if (fresh) { mem.set(base, fresh); await writeDisk(fresh); }
          return fresh;
        })
        .catch(() => null)
        .finally(() => inflight.delete(base)),
    );
  }
  const fresh = await inflight.get(base)!;
  return fresh ?? cur ?? null; // stale-but-good beats nothing
}

/** Rate to convert 1 unit of `base` into `to`, or null if unknown. */
export function rateFor(r: Rates | null, to: string): number | null {
  if (!r) return null;
  const v = r.rates[to];
  return typeof v === 'number' && v > 0 ? v : null;
}
