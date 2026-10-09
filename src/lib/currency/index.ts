// Central "currency brain": decides which currency a visitor sees and at what rate.
// Used by the /api/currency endpoint; any page or component can rely on it.
// Base amounts are never changed — this only produces display information.
import { site } from '../../data/site';
import { currencyForCountry, isValidCurrency } from './countryCurrency';
import { countryFromIp } from './geo';
import { getRates, rateFor } from './rates';
import { formatSpec } from './format';

export { formatMoney, formatSpec } from './format';
export { currencyForCountry, isValidCurrency } from './countryCurrency';

/** The site's configured base currency (what amounts are stored in). */
export const BASE_CURRENCY = site.currency.trim().toUpperCase();

export type DisplayCurrency = {
  enabled: boolean;      // admin switch
  base: string;          // stored currency, e.g. OMR
  currency: string;      // currency to display
  rate: number;          // 1 base = rate × currency
  country: string | null;
  reason: 'converted' | 'same-currency' | 'disabled' | 'no-country' | 'unsupported-currency' | 'no-rate';
  format: ReturnType<typeof formatSpec>;
};

function fallback(enabled: boolean, country: string | null, reason: DisplayCurrency['reason']): DisplayCurrency {
  return { enabled, base: BASE_CURRENCY, currency: BASE_CURRENCY, rate: 1, country, reason, format: formatSpec(BASE_CURRENCY) };
}

/**
 * Work out the display currency for a visitor.
 * @param ip       visitor's public IP
 * @param enabled  admin "Automatic Currency Conversion" setting
 * @param countryOverride  test-only country code (honoured only when the caller allows it)
 */
export async function resolveDisplayCurrency(ip: string, enabled: boolean, countryOverride?: string | null): Promise<DisplayCurrency> {
  if (!enabled) return fallback(false, null, 'disabled');

  const country = countryOverride ? countryOverride.toUpperCase() : await countryFromIp(ip);
  if (!country) return fallback(true, null, 'no-country');

  const currency = currencyForCountry(country);
  if (!currency || !isValidCurrency(currency)) return fallback(true, country, 'unsupported-currency');
  if (currency === BASE_CURRENCY) return { ...fallback(true, country, 'same-currency') };

  const rate = rateFor(await getRates(BASE_CURRENCY), currency);
  if (!rate) return fallback(true, country, 'no-rate');

  return { enabled: true, base: BASE_CURRENCY, currency, rate, country, reason: 'converted', format: formatSpec(currency) };
}

/** Convert a stored base amount for display (never mutates the stored amount). */
export function convert(amount: number, rate: number): number {
  return Number.isFinite(amount) && Number.isFinite(rate) && rate > 0 ? amount * rate : amount;
}
