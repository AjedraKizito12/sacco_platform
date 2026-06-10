import { Button, Card } from "@sacco/ui";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";

export default function SubscriptionPastDue() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl place-items-center p-8">
      <Card className="w-full p-10 text-center">
        <AlertTriangle
          size={48}
          strokeWidth={1.75}
          className="mx-auto mb-4 text-[var(--text-warning)]"
          aria-hidden
        />
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Subscription past due — payment required
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Your tenant&apos;s subscription is past due and the grace period has
          expired. Settle the outstanding invoice to restore access. Contact
          finance if you believe this is in error.
        </p>
        <div className="flex justify-center gap-3">
          <Button asChild>
            <Link href="/billing">View invoices</Link>
          </Button>
          <Button variant="secondary" asChild>
            <a href="mailto:finance@sacco.example">Contact finance</a>
          </Button>
        </div>
      </Card>
    </main>
  );
}
