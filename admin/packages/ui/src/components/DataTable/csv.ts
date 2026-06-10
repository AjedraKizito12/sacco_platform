/**
 * Serialize rows to RFC-4180-ish CSV. Sufficient for client-side download
 * of small page-sized datasets. Reporting endpoints (sub-plan 29) handle
 * large exports server-side.
 */
export function rowsToCsv(
  rows: Record<string, unknown>[],
  columns: { key: string; header: string }[],
): string {
  const escape = (val: unknown): string => {
    if (val == null) return "";
    const str = String(val);
    if (/[",\n]/.test(str)) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const header = columns.map((c) => escape(c.header)).join(",");
  const body = rows
    .map((row) => columns.map((c) => escape(row[c.key])).join(","))
    .join("\n");
  return `${header}\n${body}\n`;
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
