// admin/apps/portal/app/(tenant-authed)/reports/fee-collection/_components/FeeCollectionFilter.tsx
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

export interface FeeTypeChoice {
  id: string;
  label: string;
}

export function FeeCollectionFilter({ feeTypes }: { feeTypes: FeeTypeChoice[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const [from, setFrom] = useState(params.get("from_date") ?? "");
  const [to, setTo] = useState(params.get("to_date") ?? "");
  const [feeTypeId, setFeeTypeId] = useState(params.get("fee_type_id") ?? "all");

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="from_date">From</Label>
        <DateInput id="from_date" value={from} onValueChange={setFrom} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="to_date">To</Label>
        <DateInput id="to_date" value={to} onValueChange={setTo} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="fee_type_id">Fee type</Label>
        <Select value={feeTypeId} onValueChange={setFeeTypeId}>
          <SelectTrigger id="fee_type_id" className="w-60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All fee types</SelectItem>
            {feeTypes.map((f) => (
              <SelectItem key={f.id} value={f.id}>{f.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button
        type="button"
        onClick={() =>
          router.push(
            `/reports/fee-collection?${new URLSearchParams({
              ...(from ? { from_date: from } : {}),
              ...(to ? { to_date: to } : {}),
              ...(feeTypeId && feeTypeId !== "all" ? { fee_type_id: feeTypeId } : {}),
            }).toString()}`,
          )
        }
      >
        Apply
      </Button>
    </div>
  );
}
