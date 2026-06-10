"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_PREFIX = "sacco_draft:";

export interface UseDraftAutoSaveOptions<TValue> {
  /** Stable key for the draft, e.g., "loan-application:user-uuid". */
  formKey: string;
  /** Current form values to persist. */
  values: TValue;
  /** Debounce window for saves. Default 750ms. */
  debounceMs?: number;
  /** Skip writes (useful while the form is hydrating). */
  enabled?: boolean;
}

export interface UseDraftAutoSaveResult<TValue> {
  /** Read any previously-saved draft. Returns null when none exists. */
  restore(): TValue | null;
  /** Drop the saved draft (call after a successful submit). */
  clear(): void;
  /** ISO timestamp of the last successful save, or null. */
  lastSavedAt: string | null;
}

/**
 * Debounced localStorage persistence for in-progress forms. The hook does
 * NOT control the form — it just shadows `values` to storage and exposes a
 * `restore()` the consumer can call from a "You have unsaved changes…
 * Restore?" prompt.
 */
export function useDraftAutoSave<TValue>(
  options: UseDraftAutoSaveOptions<TValue>,
): UseDraftAutoSaveResult<TValue> {
  const { formKey, values, debounceMs = 750, enabled = true } = options;
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      try {
        const payload = {
          values,
          savedAt: new Date().toISOString(),
        };
        window.localStorage.setItem(
          `${STORAGE_PREFIX}${formKey}`,
          JSON.stringify(payload),
        );
        setLastSavedAt(payload.savedAt);
      } catch {
        // Quota or serialisation error — drop silently. The consumer can
        // surface "Couldn't save your draft" via a different signal if needed.
      }
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [debounceMs, enabled, formKey, values]);

  const restore = useCallback((): TValue | null => {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${formKey}`);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { values?: TValue };
      return parsed.values ?? null;
    } catch {
      return null;
    }
  }, [formKey]);

  const clear = useCallback(() => {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(`${STORAGE_PREFIX}${formKey}`);
    setLastSavedAt(null);
  }, [formKey]);

  return { restore, clear, lastSavedAt };
}
