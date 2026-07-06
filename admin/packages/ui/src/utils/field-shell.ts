/**
 * Shared chrome for the composite text-like fields (MoneyInput,
 * PercentageInput, DateInput). These wrap a bare <input> in a flex shell so
 * they can sit an affixed currency/percent token or calendar trigger next to
 * the value. The shell mirrors the base <Input> control — same height, hover,
 * focus, disabled and error states — so the whole family reads as one control.
 *
 * Error state is driven by the `aria-invalid="true"` the consumer already
 * forwards from `<FormField>`; no extra prop is needed on the field.
 */
export const fieldShellClass = [
  "flex h-[var(--height-control)] items-center gap-2 rounded-[var(--radius-md)] px-3",
  "border border-[var(--border-default)] bg-[var(--surface-elevated)]",
  "text-[var(--text-primary)] transition-colors duration-150",
  "hover:border-[var(--border-strong)]",
  "focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--shadow-focus)]",
  "has-[:disabled]:cursor-not-allowed has-[:disabled]:border-[var(--border-subtle)] has-[:disabled]:bg-[var(--surface-disabled)]",
  "has-[[aria-invalid=true]]:border-[var(--border-danger)]",
  "has-[[aria-invalid=true]]:focus-within:shadow-[var(--shadow-focus-danger)]",
].join(" ");

/**
 * The bare <input> inside a field shell. Transparent background (the shell
 * owns the surface), body type token, tabular + lining numerals, and the
 * shared placeholder/disabled treatment from the base <Input>.
 */
export const fieldInputClass = [
  "h-full flex-1 bg-transparent text-[var(--text-body)] text-[var(--text-primary)] outline-none",
  "placeholder:text-[var(--text-disabled)] disabled:cursor-not-allowed",
  "[font-feature-settings:'tnum'_1,'lnum'_1]",
].join(" ");

/**
 * Numeric variant: right-aligned, with the native number spinners stripped so
 * the affix token stays put. Used by MoneyInput and PercentageInput.
 */
export const fieldNumericInputClass = [
  fieldInputClass,
  "text-right",
  "[appearance:textfield] [-webkit-appearance:textfield]",
  "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
].join(" ");

/**
 * className passed to the calendar `<PopoverContent>`. Overrides the popover's
 * default fixed width so the day grid (and the two-month range picker) renders
 * at its natural width with even padding instead of clipping the right columns.
 */
export const calendarPopoverClass = "w-auto p-3";
