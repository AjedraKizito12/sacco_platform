const TONE: Record<string, string> = {
  insert: "text-[var(--text-success)]",
  update: "text-[var(--text-primary)]",
  delete: "text-[var(--text-danger)]",
};

export function AuditOperationLabel({ operation }: { operation: string }) {
  return (
    <span className={`font-medium ${TONE[operation] ?? "text-[var(--text-secondary)]"}`}>
      {operation}
    </span>
  );
}
