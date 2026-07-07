"use client";

import { useState } from "react";

function renderValue(v: unknown): string {
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function isUuidish(v: unknown): boolean {
  return typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(v);
}

export interface PayloadViewProps {
  payload: Record<string, unknown>;
}

export function PayloadView({ payload }: PayloadViewProps) {
  const [rawOpen, setRawOpen] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
        {Object.entries(payload).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-2">
            <span className="text-[var(--text-secondary)]">{k}</span>
            <span
              className={
                isUuidish(v)
                  ? "font-mono text-[13px] text-[var(--text-primary)]"
                  : "text-[var(--text-primary)]"
              }
            >
              {renderValue(v)}
            </span>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setRawOpen((o) => !o)}
        className="self-start text-[13px] text-[var(--text-link)]"
      >
        {rawOpen ? "Hide raw JSON" : "View raw JSON"}
      </button>
      {rawOpen ? (
        <pre className="overflow-auto rounded-md bg-[var(--surface-sunken)] p-3 text-[12px] text-[var(--text-primary)]">
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
