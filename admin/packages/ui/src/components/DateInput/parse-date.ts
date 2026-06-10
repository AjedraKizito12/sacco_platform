import { isValid, parse } from "date-fns";

/**
 * Accept "DD/MM/YYYY" or "YYYY-MM-DD" (the design-system spec, line 603).
 * Returns the ISO date string ("YYYY-MM-DD") on success, null on failure.
 */
export function parseTypedDate(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  for (const fmt of ["yyyy-MM-dd", "dd/MM/yyyy"] as const) {
    const parsed = parse(trimmed, fmt, new Date());
    if (isValid(parsed)) {
      const yyyy = parsed.getFullYear().toString().padStart(4, "0");
      const mm = (parsed.getMonth() + 1).toString().padStart(2, "0");
      const dd = parsed.getDate().toString().padStart(2, "0");
      return `${yyyy}-${mm}-${dd}`;
    }
  }
  return null;
}

/** Format an ISO date as `DD/MM/YYYY` (for typed input). */
export function formatDateForInput(iso: string): string {
  if (!iso) return "";
  const [yyyy, mm, dd] = iso.split("-");
  if (!yyyy || !mm || !dd) return "";
  return `${dd}/${mm}/${yyyy}`;
}
