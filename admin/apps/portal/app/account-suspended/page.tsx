import { Button, Card } from "@sacco/ui";
import { Ban } from "lucide-react";

export default function AccountSuspended() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl place-items-center p-8">
      <Card className="w-full p-10 text-center">
        <Ban
          size={48}
          strokeWidth={1.75}
          className="mx-auto mb-4 text-[var(--text-danger)]"
          aria-hidden
        />
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Account suspended
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Access to this tenant has been suspended. Contact the platform
          administrator to restore it.
        </p>
        <Button asChild>
          <a href="mailto:support@sacco.example">Contact platform admin</a>
        </Button>
      </Card>
    </main>
  );
}
