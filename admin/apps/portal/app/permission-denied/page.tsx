import { Button, Card } from "@sacco/ui";
import { Lock } from "lucide-react";
import Link from "next/link";

export default function PermissionDenied() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl place-items-center p-8">
      <Card className="w-full p-10 text-center">
        <Lock
          size={48}
          strokeWidth={1.75}
          className="mx-auto mb-4 text-[var(--icon-default)]"
          aria-hidden
        />
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          You don&apos;t have permission to view this section
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Contact your administrator if you believe this is wrong.
        </p>
        <Button asChild>
          <Link href="/">Back to dashboard</Link>
        </Button>
      </Card>
    </main>
  );
}
