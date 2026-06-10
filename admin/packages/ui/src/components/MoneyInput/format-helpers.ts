import { getCurrencyConfig } from "../../utils/currency";

/**
 * Strip everything except digits, decimal point, and leading minus.
 * Tolerates the user pasting "UGX 1,234.50" or typing as they go.
 */
export function stripFormatting(input: string): string {
  if (!input) return "";
  const leadingMinus = input.trimStart().startsWith("-") ? "-" : "";
  const digits = input.replace(/[^0-9.]/g, "");
  const firstDot = digits.indexOf(".");
  if (firstDot === -1) return `${leadingMinus}${digits}`;
  const integer = digits.slice(0, firstDot);
  const fraction = digits.slice(firstDot + 1).replace(/\./g, "");
  return `${leadingMinus}${integer}.${fraction}`;
}

/**
 * Add thousands separators while the user types. Preserves a trailing dot
 * and trailing zeros so "12." doesn't collapse to "12".
 */
export function formatTyping(stripped: string): string {
  if (!stripped) return "";
  const negative = stripped.startsWith("-");
  const body = negative ? stripped.slice(1) : stripped;
  const [intPart, fracPart] = body.split(".");
  const withThousands = (intPart ?? "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const result =
    fracPart === undefined ? withThousands : `${withThousands}.${fracPart}`;
  return `${negative ? "-" : ""}${result}`;
}

/**
 * On blur, canonicalise to the currency's decimal precision.
 * "12" + UGX (0 decimals) → "12"
 * "12" + USD (2 decimals) → "12.00"
 * "12.5" + USD → "12.50"
 * "12.567" + USD → "12.57"
 * "" → ""  (we leave empty values untouched so RHF can flag "required")
 */
export function canonicalise(
  stripped: string,
  currencyCode: string,
): string {
  if (!stripped || stripped === "-") return "";
  const config = getCurrencyConfig(currencyCode);
  const numeric = Number.parseFloat(stripped);
  if (!Number.isFinite(numeric)) return "";
  return numeric.toFixed(config.decimals);
}
