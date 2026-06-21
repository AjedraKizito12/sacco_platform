"use client";

import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import {
  formatAuditTimestamp,
  formatDate,
  formatDateTime,
  formatRelativeTime,
} from "../../utils/format";
import { useTenantCurrency } from "../../context/TenantCurrency";

const numericClass = "[font-feature-settings:'tnum'_1,'lnum'_1]";

export interface FormattedDateProps extends HTMLAttributes<HTMLSpanElement> {
  /** ISO date (YYYY-MM-DD) or full ISO timestamp. */
  value: string | Date;
}

export function FormattedDate({ value, className, ...props }: FormattedDateProps) {
  return (
    <span className={cn(numericClass, className)} {...props}>
      {formatDate(value)}
    </span>
  );
}

export interface FormattedDateTimeProps extends HTMLAttributes<HTMLSpanElement> {
  value: string | Date;
  /** Override the tenant's default timezone. */
  timeZone?: string;
}

export function FormattedDateTime({
  value,
  timeZone,
  className,
  ...props
}: FormattedDateTimeProps) {
  const ctx = useTenantCurrency();
  return (
    <span className={cn(numericClass, className)} {...props}>
      {formatDateTime(value, timeZone ?? ctx.timeZone)}
    </span>
  );
}

export interface AuditTimestampProps extends HTMLAttributes<HTMLSpanElement> {
  value: string | Date;
  timeZone?: string;
}

export function AuditTimestamp({
  value,
  timeZone,
  className,
  ...props
}: AuditTimestampProps) {
  const ctx = useTenantCurrency();
  return (
    <span className={cn(numericClass, className)} {...props}>
      {formatAuditTimestamp(value, timeZone ?? ctx.timeZone)}
    </span>
  );
}

export interface RelativeTimeProps extends HTMLAttributes<HTMLSpanElement> {
  value: string | Date;
  /** Custom "now" for testing. */
  now?: Date;
}

export function RelativeTime({
  value,
  now,
  className,
  ...props
}: RelativeTimeProps) {
  return (
    <span
      className={cn(numericClass, className)}
      title={typeof value === "string" ? value : value.toISOString()}
      {...props}
    >
      {formatRelativeTime(value, now)}
    </span>
  );
}
