"use client";

import { CalendarDays } from "lucide-react";
import { useState } from "react";
import { DayPicker, type DateRange } from "react-day-picker";
import "react-day-picker/style.css";
import { cn } from "../../utils/cn";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { formatDateForInput, parseTypedDate } from "./parse-date";

export interface DateRangeValue {
  from: string;
  to: string;
}

export interface DateRangeInputProps {
  value: DateRangeValue;
  onValueChange(next: DateRangeValue): void;
  className?: string;
  /** Aria label for the popover trigger. */
  triggerAriaLabel?: string;
}

export function DateRangeInput({
  value,
  onValueChange,
  className,
  triggerAriaLabel = "Open date range calendar",
}: DateRangeInputProps) {
  const [open, setOpen] = useState(false);
  const [fromTyped, setFromTyped] = useState(formatDateForInput(value.from));
  const [toTyped, setToTyped] = useState(formatDateForInput(value.to));

  const commit = (key: "from" | "to", typed: string) => {
    const parsed = parseTypedDate(typed);
    if (parsed) {
      onValueChange({ ...value, [key]: parsed });
    } else if (typed.trim() === "") {
      onValueChange({ ...value, [key]: "" });
    }
  };

  // react-day-picker's DateRange requires `from`. When only `to` is set,
  // treat it as a one-day range whose start = end so the calendar lights
  // up consistently.
  const fromAnchor = value.from || value.to;
  const selected: DateRange | undefined = fromAnchor
    ? {
        from: new Date(`${fromAnchor}T00:00:00`),
        ...(value.to && value.from !== value.to
          ? { to: new Date(`${value.to}T00:00:00`) }
          : {}),
      }
    : undefined;

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <input
        aria-label="From"
        placeholder="DD/MM/YYYY"
        value={fromTyped}
        onChange={(e) => setFromTyped(e.target.value)}
        onBlur={() => commit("from", fromTyped)}
        className="h-[var(--height-control-md)] w-[140px] rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] px-3 text-[14px] outline-none focus:border-[var(--border-focus)]"
      />
      <span aria-hidden="true" className="text-[var(--text-tertiary)]">
        →
      </span>
      <input
        aria-label="To"
        placeholder="DD/MM/YYYY"
        value={toTyped}
        onChange={(e) => setToTyped(e.target.value)}
        onBlur={() => commit("to", toTyped)}
        className="h-[var(--height-control-md)] w-[140px] rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] px-3 text-[14px] outline-none focus:border-[var(--border-focus)]"
      />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={triggerAriaLabel}
            className="grid h-[var(--height-control-md)] w-[var(--height-control-md)] place-content-center rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)]"
          >
            <CalendarDays size={16} strokeWidth={1.75} />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="p-2">
          <DayPicker
            mode="range"
            numberOfMonths={2}
            {...(selected ? { selected } : {})}
            onSelect={(range) => {
              if (!range) return;
              const fmt = (d?: Date) => {
                if (!d) return "";
                const y = d.getFullYear().toString().padStart(4, "0");
                const m = (d.getMonth() + 1).toString().padStart(2, "0");
                const dd = d.getDate().toString().padStart(2, "0");
                return `${y}-${m}-${dd}`;
              };
              const next = { from: fmt(range.from), to: fmt(range.to) };
              onValueChange(next);
              setFromTyped(formatDateForInput(next.from));
              setToTyped(formatDateForInput(next.to));
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
