// admin/apps/portal/app/(tenant-authed)/reports/income-statement/_components/DateRangeFilter.tsx
"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, DateInput, Label } from "@sacco/ui";

export function DateRangeFilter({ basePath }: { basePath: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [from, setFrom] = useState(params.get("from_date") ?? "");
  const [to, setTo] = useState(params.get("to_date") ?? "");
  return (
    <div className="flex items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="from_date">From</Label>
        <DateInput id="from_date" value={from} onValueChange={setFrom} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="to_date">To</Label>
        <DateInput id="to_date" value={to} onValueChange={setTo} />
      </div>
      <Button
        type="button"
        onClick={() =>
          router.push(
            `${basePath}?${new URLSearchParams({
              ...(from ? { from_date: from } : {}),
              ...(to ? { to_date: to } : {}),
            }).toString()}`,
          )
        }
      >
        Apply
      </Button>
    </div>
  );
}
