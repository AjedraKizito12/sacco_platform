import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { formatMoney } from "../../utils/format";
import { useTenantCurrency } from "../../context/TenantCurrency";

export interface MoneyProps extends HTMLAttributes<HTMLSpanElement> {
  /** Decimal-as-string amount per CLAUDE.md rule #5. */
  amount: string;
  /** Override the provider's currency. */
  currency?: string;
  /** Render in a larger style for KPI cards. */
  size?: "default" | "large";
}

export function Money({
  amount,
  currency,
  size = "default",
  className,
  ...props
}: MoneyProps) {
  const provider = useTenantCurrency();
  const effectiveCurrency = currency ?? provider.currency;
  const formatted = formatMoney(amount, effectiveCurrency);
  const isNegative = formatted.startsWith("-");
  return (
    <span
      className={cn(
        "[font-feature-settings:'tnum'_1,'lnum'_1]",
        size === "large" && "text-[28px] font-semibold leading-tight",
        isNegative && "text-[var(--text-danger)]",
        className,
      )}
      data-currency={effectiveCurrency}
      data-amount={amount}
      {...props}
    >
      {formatted}
    </span>
  );
}
