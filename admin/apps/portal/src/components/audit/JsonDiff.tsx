function fmt(v: unknown): string {
  if (v === undefined) return "—";
  if (v === null) return "null";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export interface JsonDiffProps {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export function JsonDiff({ before, after }: JsonDiffProps) {
  const keys = Array.from(
    new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]),
  ).sort();

  if (keys.length === 0) {
    return <p className="text-[var(--text-tertiary)]">No field-level detail.</p>;
  }

  return (
    <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
      <div className="flex gap-4 py-1 text-[12px] text-[var(--text-tertiary)]">
        <span className="w-40">Field</span>
        <span className="flex-1">Before</span>
        <span className="flex-1">After</span>
      </div>
      {keys.map((k) => {
        const b = before?.[k];
        const a = after?.[k];
        const changed = fmt(b) !== fmt(a);
        return (
          <div key={k} className={`flex gap-4 py-1.5 ${changed ? "" : "opacity-60"}`}>
            <span className="w-40 font-mono text-[12px] text-[var(--text-secondary)]">{k}</span>
            <span className="flex-1 font-mono text-[12px] text-[var(--text-primary)]">{fmt(b)}</span>
            <span className="flex-1 font-mono text-[12px] text-[var(--text-primary)]">{fmt(a)}</span>
          </div>
        );
      })}
    </div>
  );
}
