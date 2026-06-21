// admin/apps/portal/app/(tenant-authed)/reports/savings-statement/_components/SavingsStatementFilter.tsx
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

export interface MemberChoice {
  id: string;
  label: string;
}

export function SavingsStatementFilter({ members }: { members: MemberChoice[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const [memberId, setMemberId] = useState(params.get("member_id") ?? "");
  const [from, setFrom] = useState(params.get("from_date") ?? "");
  const [to, setTo] = useState(params.get("to_date") ?? "");

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="member_id">Member</Label>
        <Select value={memberId} onValueChange={setMemberId}>
          <SelectTrigger id="member_id" className="w-72">
            <SelectValue placeholder="Choose a member…" />
          </SelectTrigger>
          <SelectContent>
            {members.map((m) => (
              <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
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
            `/reports/savings-statement?${new URLSearchParams({
              ...(memberId ? { member_id: memberId } : {}),
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
