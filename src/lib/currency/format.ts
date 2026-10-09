// Money formatting per currency, using the built-in Intl.NumberFormat.
// Symbol currencies show the symbol (₹1,000 · $12.00 · £8.50 · €9.20);
// Gulf currencies show the code (AED 44.00 · OMR 4.60 · SAR 45.00).

const LOCALE: Record<string, string> = {
  INR: 'en-IN', USD: 'en-US', GBP: 'en-GB', EUR: 'en-IE', AED: 'en-AE', OMR: 'en-OM',
  SAR: 'en-SA', QAR: 'en-QA', KWD: 'en-KW', BHD: 'en-BH', JPY: 'ja-JP', PKR: 'en-PK',
};
const CODE_STYLE = new Set(['AED', 'OMR', 'SAR', 'QAR', 'KWD', 'BHD']);

/** Decimal places used in prices: none for large-unit currencies, else 2. */
export function decimalsFor(currency: string): number {
  return ['INR', 'JPY', 'KRW', 'IDR', 'VND', 'PKR', 'LKR', 'HUF', 'CLP', 'COP', 'IRR', 'UGX', 'TZS'].includes(currency) ? 0 : 2;
}

export function formatMoney(amount: number, currency: string): string {
  if (!Number.isFinite(amount)) amount = 0;
  const d = decimalsFor(currency);
  try {
    return new Intl.NumberFormat(LOCALE[currency] ?? 'en', {
      style: 'currency',
      currency,
      currencyDisplay: CODE_STYLE.has(currency) ? 'code' : 'narrowSymbol',
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }).format(amount).replace(/ /g, ' ');
  } catch {
    return `${currency} ${amount.toFixed(d)}`;
  }
}

/** Plain description the browser can use to format on its own (no extra server calls). */
export function formatSpec(currency: string) {
  return {
    locale: LOCALE[currency] ?? 'en',
    display: CODE_STYLE.has(currency) ? 'code' : 'narrowSymbol',
    decimals: decimalsFor(currency),
  };
}
