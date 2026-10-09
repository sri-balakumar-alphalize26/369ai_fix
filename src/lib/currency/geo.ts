// Public IP → country code (server-side). Primary: ipwho.is, fallback: ipapi.co.
// Results are cached per IP for 24 h (in memory, max 10,000 IPs) so repeat visits cost nothing.

const DAY = 24 * 3600 * 1000;
const MAX = 10_000;
const cache = new Map<string, { cc: string | null; at: number }>();

/** Private, loopback and link-local addresses can't be located. */
export function isPublicIp(ip: string): boolean {
  if (!ip) return false;
  const v = ip.replace(/^::ffff:/, '');
  if (v === '::1' || v === '127.0.0.1' || v === 'localhost') return false;
  if (/^(10\.|192\.168\.|169\.254\.|127\.)/.test(v)) return false;
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(v)) return false;
  if (/^(fc|fd|fe80)/i.test(v)) return false;
  return /^[\d.]+$/.test(v) || /^[0-9a-f:]+$/i.test(v);
}

/** Best guess at the visitor's public IP from proxy headers, else the socket address. */
export function clientIp(request: Request, socketAddress?: string): string {
  const fwd = request.headers.get('x-forwarded-for');
  if (fwd) return fwd.split(',')[0].trim();
  return request.headers.get('x-real-ip') || request.headers.get('cf-connecting-ip') || socketAddress || '';
}

async function getJson(url: string, ms = 3000): Promise<any> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, headers: { accept: 'application/json' } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

// Tried in order; the first valid 2-letter country wins. All free, no API key.
const PROVIDERS: ((ip: string) => Promise<unknown>)[] = [
  async (ip) => (await getJson(`https://api.country.is/${encodeURIComponent(ip)}`))?.country,
  async (ip) => { const j = await getJson(`https://ipwho.is/${encodeURIComponent(ip)}?fields=success,country_code`); return j?.success !== false && j?.country_code; },
  async (ip) => (await getJson(`https://ipapi.co/${encodeURIComponent(ip)}/json/`))?.country_code,
];

async function lookup(ip: string): Promise<string | null> {
  for (const ask of PROVIDERS) {
    try {
      const v = await ask(ip);
      if (typeof v === 'string' && /^[A-Z]{2}$/i.test(v)) return v.toUpperCase();
    } catch {
      /* try the next provider */
    }
  }
  return null;
}

/** Development only: country of this machine's own public IP (localhost visitors have none). */
let selfCountry: string | null = null;
export async function countryOfThisMachine(): Promise<string | null> {
  if (selfCountry) return selfCountry; // remember a success; retry after a failure
  try {
    const j = await getJson('https://api.country.is/');
    if (typeof j?.country === 'string' && /^[A-Z]{2}$/.test(j.country)) selfCountry = j.country;
  } catch { /* stay null and try again next time */ }
  return selfCountry;
}

/** Country code for a public IP, or null if it can't be found. Never throws. */
export async function countryFromIp(ip: string): Promise<string | null> {
  if (!isPublicIp(ip)) return null;
  const hit = cache.get(ip);
  // a found country is remembered for a day; a failed lookup only for 10 minutes
  if (hit && Date.now() - hit.at < (hit.cc ? DAY : 10 * 60 * 1000)) return hit.cc;
  // visitors from the same IP arriving together share one lookup
  let job = pending.get(ip);
  if (!job) {
    job = lookup(ip).then((cc) => {
      if (cache.size >= MAX) cache.delete(cache.keys().next().value!); // drop the oldest
      cache.set(ip, { cc, at: Date.now() });
      return cc;
    }).finally(() => pending.delete(ip));
    pending.set(ip, job);
  }
  return job;
}
const pending = new Map<string, Promise<string | null>>();
