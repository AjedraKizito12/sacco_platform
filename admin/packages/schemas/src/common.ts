import { z } from "zod";

/**
 * Money is stored as Decimal-as-string on the wire (matches the backend's
 * Numeric(19,4) / DECIMAL(19,4) columns and CLAUDE.md rule #5). The portal
 * never sends a float.
 *
 * The schema accepts up to 4 decimal places. Per-currency precision (UGX → 0,
 * KES/USD → 2) is enforced at the <MoneyInput> layer (sub-plan 11), not here.
 */
export const moneyString = (opts?: {
  min?: string;
  max?: string;
  allowNegative?: boolean;
}) => {
  const pattern = opts?.allowNegative
    ? /^-?\d+(\.\d{1,4})?$/
    : /^\d+(\.\d{1,4})?$/;
  let schema: z.ZodType<string> = z
    .string()
    .trim()
    .regex(pattern, "Must be a decimal with up to 4 places");

  if (opts?.min !== undefined) {
    const minVal = opts.min;
    schema = schema.refine(
      (v) => Number.parseFloat(v) >= Number.parseFloat(minVal),
      `Must be ≥ ${minVal}`,
    );
  }
  if (opts?.max !== undefined) {
    const maxVal = opts.max;
    schema = schema.refine(
      (v) => Number.parseFloat(v) <= Number.parseFloat(maxVal),
      `Must be ≤ ${maxVal}`,
    );
  }
  return schema;
};

/**
 * Percentage is also Decimal-as-string with up to 2 decimal places.
 * Default range 0-100.
 */
export const percentageString = (opts?: { min?: number; max?: number }) => {
  const min = opts?.min ?? 0;
  const max = opts?.max ?? 100;
  return z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,2})?$/, "Must be a percentage with up to 2 places")
    .refine((v) => Number.parseFloat(v) >= min, `Must be ≥ ${min}`)
    .refine((v) => Number.parseFloat(v) <= max, `Must be ≤ ${max}`);
};

/** Whole-number string (integer-as-string on the wire; Pydantic lax-coerces). */
export const intString = (opts?: { min?: number }) => {
  let schema: z.ZodType<string> = z
    .string()
    .trim()
    .regex(/^\d+$/, "Must be a whole number");
  if (opts?.min !== undefined) {
    const m = opts.min;
    schema = schema.refine((v) => Number.parseInt(v, 10) >= m, `Must be ≥ ${m}`);
  }
  return schema;
};

/** ISO-3 currency code, uppercase. UGX-only in v1 but kept flexible. */
export const currencyCode = z
  .string()
  .trim()
  .regex(/^[A-Z]{3}$/, "Must be a 3-letter currency code");

/** UUID v4 string from the backend (validates v1-5 patterns inclusively). */
export const uuid = z.string().uuid("Must be a valid UUID");

/** ISO-8601 date string (YYYY-MM-DD). */
export const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Must be YYYY-MM-DD");

/** ISO-8601 datetime string. */
export const isoDateTime = z.string().datetime({
  message: "Must be an ISO-8601 datetime",
});

/**
 * Cursor pagination shape matching the audit log API (P1.7-06): opaque
 * base64 cursor, integer limit capped at 100.
 */
export const cursorPagination = () =>
  z.object({
    cursor: z.string().optional(),
    limit: z.coerce.number().int().min(1).max(100).optional(),
  });

/**
 * Idempotency key — UUID v4-ish; min length 8 enforced by the billing
 * PaymentRecordIn (backend Pydantic validator). We pass-through; the
 * api-client (sub-plan 05) injects a UUID v7 when none is provided.
 */
export const idempotencyKey = z.string().min(8);

export type Money = z.infer<ReturnType<typeof moneyString>>;
export type Percentage = z.infer<ReturnType<typeof percentageString>>;
export type CurrencyCode = z.infer<typeof currencyCode>;
export type UUID = z.infer<typeof uuid>;
export type ISODate = z.infer<typeof isoDate>;
export type ISODateTime = z.infer<typeof isoDateTime>;
