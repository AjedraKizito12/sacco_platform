import { format, formatDistance, parseISO } from "date-fns";
import { getCurrencyConfig } from "./currency";

/**
 * Format a Decimal-as-string money value for display.
 * Examples:
 *   formatMoney("1234567", "UGX") → "UGX 1,234,567"
 *   formatMoney("-50.5", "USD")   → "-USD 50.50"
 *   formatMoney("0", "UGX")        → "UGX 0"
 */
export function formatMoney(amount: string, currencyCode: string): string {
  const config = getCurrencyConfig(currencyCode);
  const numeric = Number.parseFloat(amount);
  if (!Number.isFinite(numeric)) {
    // Invalid input — render as-is rather than throwing.
    return `${config.code} ${amount}`;
  }
  const absolute = Math.abs(numeric);
  const formatter = new Intl.NumberFormat(config.locale, {
    minimumFractionDigits: config.decimals,
    maximumFractionDigits: config.decimals,
    useGrouping: true,
  });
  const formatted = formatter.format(absolute);
  return `${numeric < 0 ? "-" : ""}${config.code} ${formatted}`;
}

/**
 * Format a percentage from a Decimal-as-string value. Always 2 decimals.
 */
export function formatPercentage(value: string): string {
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return `${value}%`;
  return `${numeric.toFixed(2)}%`;
}

/**
 * Format a non-decimal count with locale thousands separator.
 */
export function formatCount(value: number, locale = "en-UG"): string {
  return new Intl.NumberFormat(locale, { useGrouping: true }).format(value);
}

// ── Dates ─────────────────────────────────────────────────────────────────────

/** Render YYYY-MM-DD or ISO datetime as "28 May 2026". */
export function formatDate(value: string | Date): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return format(date, "d MMM yyyy");
}

/** Render an ISO datetime as "28 May 2026, 14:32" in the given timezone. */
export function formatDateTime(
  value: string | Date,
  timeZone?: string,
): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(date);
}

/** Render an audit timestamp: "28 May 2026, 14:32:07 EAT". */
export function formatAuditTimestamp(
  value: string | Date,
  timeZone?: string,
): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone,
    timeZoneName: "short",
  }).format(date);
}

/** "2 hours ago" etc. Falls back to formatDate() after 7 days. */
export function formatRelativeTime(
  value: string | Date,
  now: Date = new Date(),
): string {
  const date = typeof value === "string" ? parseISO(value) : value;
  const ageMs = now.getTime() - date.getTime();
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
  if (Math.abs(ageMs) > sevenDaysMs) {
    return formatDate(date);
  }
  // formatDistance(date, baseDate) is testable; formatDistanceToNow uses the
  // real clock and would ignore the injected `now`.
  return formatDistance(date, now, { addSuffix: true });
}
