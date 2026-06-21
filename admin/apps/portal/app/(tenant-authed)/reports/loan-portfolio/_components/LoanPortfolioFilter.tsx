// admin/apps/portal/app/(tenant-authed)/reports/loan-portfolio/_components/LoanPortfolioFilter.tsx
"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Button,
  DateInput,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";

export function LoanPortfolioFilter({ basePath }: { basePath: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [asOf, setAsOf] = useState(params.get("as_of") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "all");

  return (
    <div className="flex items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="as_of">As of</Label>
        <DateInput id="as_of" value={asOf} onValueChange={setAsOf} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="status">Status</Label>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger id="status" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="disbursed">Disbursed</SelectItem>
            <SelectItem value="in_arrears">In arrears</SelectItem>
            <SelectItem value="written_off">Written off</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button
        type="button"
        onClick={() =>
          router.push(
            `${basePath}?${new URLSearchParams({
              ...(asOf ? { as_of: asOf } : {}),
              status,
            }).toString()}`,
          )
        }
      >
        Apply
      </Button>
    </div>
  );
}
