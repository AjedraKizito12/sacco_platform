"use client";

import { useRouter } from "next/navigation";
import { Button } from "@sacco/ui";

export function RefreshButton() {
  const router = useRouter();
  return (
    <Button variant="secondary" onClick={() => router.refresh()}>
      Refresh
    </Button>
  );
}
