"use client";

import { useState } from "react";

const DIFF_FIELDS = ["is_active", "is_superuser"] as const;

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
  operationType: string;
  payload: Record<string, unknown>;
  /** Present only for platform_user.update_sensitive (fetched server-side). */
  before?: Record<string, unknown>;
}

export function PayloadView({ operationType, payload, before }: PayloadViewProps) {
  const [rawOpen, setRawOpen] = useState(false);
  const isDiff = operationType === "platform_user.update_sensitive" && before !== undefined;

  return (
    <div className="flex flex-col gap-3">
      {isDiff ? (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          <div className="flex justify-between py-2 text-[13px] text-[var(--text-tertiary)]">
            <span>Field</span>
            <span>Before → After</span>
          </div>
          {DIFF_FIELDS.map((f) => (
            <div key={f} className="flex justify-between py-2">
              <span className="text-[var(--text-secondary)]">{f}</span>
              <span className="text-[var(--text-primary)] tabular-nums">
                {renderValue(before?.[f])} → {renderValue(payload[f])}
              </span>
            </div>
          ))}
        </div>
      ) : (
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
      )}

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
