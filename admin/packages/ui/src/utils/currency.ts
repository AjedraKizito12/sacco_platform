// Single source of truth for currency precision and display.
// Adding a new currency is one row; consumers do not branch on currency.

export interface CurrencyConfig {
  /** ISO-3 code (UPPERCASE). Used as the dictionary key. */
  code: string;
  /** Number of decimals used for display + parsing. */
  decimals: number;
  /** Locale tag for Intl.NumberFormat (BCP-47). */
  locale: string;
}

export const CURRENCIES: Record<string, CurrencyConfig> = {
  UGX: { code: "UGX", decimals: 0, locale: "en-UG" },
  KES: { code: "KES", decimals: 2, locale: "en-KE" },
  TZS: { code: "TZS", decimals: 2, locale: "en-TZ" },
  RWF: { code: "RWF", decimals: 0, locale: "en-RW" },
  USD: { code: "USD", decimals: 2, locale: "en-US" },
  EUR: { code: "EUR", decimals: 2, locale: "en-IE" },
  GBP: { code: "GBP", decimals: 2, locale: "en-GB" },
};

export function getCurrencyConfig(code: string): CurrencyConfig {
  const upper = code.toUpperCase();
  return CURRENCIES[upper] ?? { code: upper, decimals: 2, locale: "en-US" };
}

export const DEFAULT_CURRENCY = "UGX";
export const DEFAULT_TIMEZONE = "Africa/Kampala";
