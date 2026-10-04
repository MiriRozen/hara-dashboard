/**
 * Money is carried as bigint micro-dollars (1 USD = 1_000_000n).
 * The API sends `*_usd` as decimal strings on purpose; parsing them to `number`
 * would lose precision, so they never go through a float.
 */
export type Micro = bigint;

const SCALE = 6;
const ONE_USD = 10n ** BigInt(SCALE);
const USD_PATTERN = /^(-)?(\d+)(?:\.(\d{1,6}))?$/;

export function parseUsd(value: string): Micro {
  const m = USD_PATTERN.exec(value.trim());
  if (!m) throw new Error(`Invalid USD amount: "${value}"`);
  const [, sign, whole = "0", frac = ""] = m;
  const micro = BigInt(whole) * ONE_USD + BigInt(frac.padEnd(SCALE, "0"));
  return sign ? -micro : micro;
}

/** "$0.7129" — the single money format used across the UI (half-up rounding). */
export function formatUsd(micro: Micro, places = 4): string {
  const negative = micro < 0n;
  const abs = negative ? -micro : micro;
  const factor = 10n ** BigInt(SCALE - places);
  const rounded = (abs + factor / 2n) / factor;
  const unit = 10n ** BigInt(places);
  const whole = (rounded / unit).toLocaleString("en-US");
  const frac = (rounded % unit).toString().padStart(places, "0");
  return `${negative ? "-" : ""}$${whole}${places > 0 ? `.${frac}` : ""}`;
}

/** Integer percent, half-up, deliberately NOT capped at 100 (a 446% overrun must read 446%). */
export function percentOf(part: Micro, whole: Micro): number | null {
  if (whole === 0n) return null;
  const negative = part < 0n !== whole < 0n;
  const p = part < 0n ? -part : part;
  const w = whole < 0n ? -whole : whole;
  const value = (p * 200n + w) / (2n * w);
  return Number(negative ? -value : value);
}

export function formatPercent(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}

/** Back to the API's wire format: "0.260000". */
export function toUsdString(micro: Micro): string {
  const negative = micro < 0n;
  const abs = negative ? -micro : micro;
  const frac = (abs % ONE_USD).toString().padStart(SCALE, "0");
  return `${negative ? "-" : ""}${abs / ONE_USD}.${frac}`;
}

export function sumMicro(values: Micro[]): Micro {
  return values.reduce((acc, v) => acc + v, 0n);
}

export function maxMicro(a: Micro, b: Micro): Micro {
  return a > b ? a : b;
}

/** Ratio for drawing only (bar widths). Never used for arithmetic on money. */
export function ratioForDisplay(part: Micro, whole: Micro): number {
  if (whole <= 0n) return 0;
  return Number((part * 10_000n) / whole) / 10_000;
}
