// Email checks shared by every email field. Plain-English messages, plus a "did you mean"
// for common typos in big providers (gmial.com → gmail.com).
const FIX: Record<string, string> = {
  'gmial.com': 'gmail.com', 'gmal.com': 'gmail.com', 'gamil.com': 'gmail.com', 'gmaill.com': 'gmail.com', 'gnail.com': 'gmail.com',
  'gmail.co': 'gmail.com', 'gmail.cm': 'gmail.com', 'gmail.con': 'gmail.com', 'gmail.om': 'gmail.com', 'gmai.com': 'gmail.com',
  'yahooo.com': 'yahoo.com', 'yaho.com': 'yahoo.com', 'yahoo.co': 'yahoo.com', 'yahoo.con': 'yahoo.com',
  'hotmial.com': 'hotmail.com', 'hotmai.com': 'hotmail.com', 'hotmail.co': 'hotmail.com', 'hotmail.con': 'hotmail.com',
  'outlok.com': 'outlook.com', 'outloo.com': 'outlook.com', 'outlook.co': 'outlook.com', 'outlook.con': 'outlook.com',
  'icloud.co': 'icloud.com', 'iclod.com': 'icloud.com',
};

export type EmailCheck = { ok: boolean; email: string; msg: string; suggest?: string };

export function checkEmail(raw: string): EmailCheck {
  const v = raw.trim();
  const bad = (msg: string, suggest?: string): EmailCheck => ({ ok: false, email: '', msg, suggest });
  if (!v) return bad('Please enter your email address.');
  if (/\s/.test(v)) return bad('Remove the spaces from the email.');
  const at = v.split('@').length - 1;
  if (at === 0) return bad('An email needs an @ — like name@gmail.com.');
  if (at > 1) return bad('Use only one @ in the email.');
  const [local, domain] = v.split('@');
  if (!local) return bad('Add your name before the @ — like name@gmail.com.');
  if (!domain) return bad('Add the ending after the @ — like gmail.com.');
  if (v.length > 254 || local.length > 64) return bad('That email is too long.');
  if (!/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)) return bad('The part before the @ has a character emails can’t use.');
  if (/^\.|\.$|\.\./.test(local)) return bad('Dots can’t be at the start, the end, or two in a row.');
  if (!domain.includes('.')) return bad(`Add the ending after ${domain} — like ${domain}.com.`);
  if (/^[.-]|[.-]$|\.\./.test(domain) || !/^[A-Za-z0-9.-]+$/.test(domain)) return bad('The part after the @ doesn’t look right.');
  const tld = domain.split('.').pop()!;
  if (!/^[A-Za-z]{2,}$/.test(tld)) return bad(`“.${tld}” isn’t a real ending — try .com or .om.`);
  const fix = FIX[domain.toLowerCase()];
  if (fix) return bad(`Did you mean ${local}@${fix}?`, `${local}@${fix}`);
  return { ok: true, email: v, msg: '' };
}
