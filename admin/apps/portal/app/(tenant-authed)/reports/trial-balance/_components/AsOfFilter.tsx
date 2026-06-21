// admin/apps/portal/app/(tenant-authed)/reports/trial-balance/_components/AsOfFilter.tsx
"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, DateInput, Label } from "@sacco/ui";

export function AsOfFilter({ basePath }: { basePath: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [asOf, setAsOf] = useState(params.get("as_of") ?? "");
  return (
    <div className="flex items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="as_of">As of</Label>
        <DateInput id="as_of" value={asOf} onValueChange={setAsOf} />
      </div>
      <Button
        type="button"
        onClick={() =>
          router.push(
            `${basePath}?${new URLSearchParams(asOf ? { as_of: asOf } : {}).toString()}`,
          )
        }
      >
        Apply
      </Button>
    </div>
  );
}
