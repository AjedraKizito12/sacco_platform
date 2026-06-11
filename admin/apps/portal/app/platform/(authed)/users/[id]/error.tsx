"use client";

import { useEffect } from "react";
import { Button, Card } from "@sacco/ui";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <Card className="flex flex-col items-start gap-3 p-6">
      <h2 className="text-[18px] font-semibold">Couldn&apos;t load this user</h2>
      <Button onClick={reset}>Try again</Button>
    </Card>
  );
}
