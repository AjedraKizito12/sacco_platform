"use client";

import { CalendarDays } from "lucide-react";
import {
  forwardRef,
  useRef,
  useState,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";
import { cn } from "../../utils/cn";
import {
  calendarPopoverClass,
  fieldInputClass,
  fieldShellClass,
} from "../../utils/field-shell";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { formatDateForInput, parseTypedDate } from "./parse-date";

export interface DateInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** ISO date YYYY-MM-DD. Empty string = no date. */
  value: string;
  onValueChange(next: string): void;
}

export const DateInput = forwardRef<HTMLInputElement, DateInputProps>(
  function DateInput(
    { value, onValueChange, onBlur, className, ...rest },
    ref,
  ) {
    const [open, setOpen] = useState(false);
    const [typed, setTyped] = useState(() => formatDateForInput(value));

    // Re-sync only when `value` itself changes externally — not on every
    // render. Tracking the last-seen value with a ref avoids stomping the
    // user's in-progress typing.
    const lastValueRef = useRef(value);
    if (lastValueRef.current !== value) {
      lastValueRef.current = value;
      setTyped(formatDateForInput(value));
    }

    const onTypedChange = (e: ChangeEvent<HTMLInputElement>) => {
      setTyped(e.target.value);
    };

    const handleBlur = (e: FocusEvent<HTMLInputElement>) => {
      const parsed = parseTypedDate(typed);
      if (parsed) {
        onValueChange(parsed);
        setTyped(formatDateForInput(parsed));
      } else if (typed.trim() === "") {
        onValueChange("");
      } else {
        // Invalid — revert to last known value.
        setTyped(formatDateForInput(value));
      }
      onBlur?.(e);
    };

    return (
      <div className={cn(fieldShellClass, className)}>
        <input
          ref={ref}
          className={fieldInputClass}
          placeholder="DD/MM/YYYY"
          value={typed}
          onChange={onTypedChange}
          onBlur={handleBlur}
          {...rest}
        />
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label="Open calendar"
              className="grid h-6 w-6 place-content-center rounded-[var(--radius-sm)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)]"
            >
              <CalendarDays size={16} strokeWidth={1.75} />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className={calendarPopoverClass}>
            <DayPicker
              mode="single"
              selected={value ? new Date(`${value}T00:00:00`) : undefined}
              onSelect={(date) => {
                if (!date) return;
                const yyyy = date.getFullYear().toString().padStart(4, "0");
                const mm = (date.getMonth() + 1).toString().padStart(2, "0");
                const dd = date.getDate().toString().padStart(2, "0");
                const iso = `${yyyy}-${mm}-${dd}`;
                onValueChange(iso);
                setTyped(formatDateForInput(iso));
                setOpen(false);
              }}
            />
          </PopoverContent>
        </Popover>
      </div>
    );
  },
);
