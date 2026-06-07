import { Badge, Button, Card, KpiCard } from "@sacco/ui";

export default function Home() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center gap-6 p-8">
      <Card className="w-full">
        <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
          Portal v1 — sub-plan 04
        </p>
        <h1 className="mb-3 text-3xl font-bold text-[var(--text-primary)]">@sacco/ui foundation</h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Tokens shared with Storybook. Components ready for the auth shell (sub-plan 07) and the
          app shell (sub-plan 08).
        </p>
        <div className="flex flex-wrap gap-2">
          <Button>Primary action</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Badge variant="success" withDot>
            Wired
          </Badge>
        </div>
      </Card>

      <div className="grid w-full grid-cols-3 gap-4">
        <KpiCard label="Total Members" value="—" />
        <KpiCard label="Outstanding Loans" value="—" />
        <KpiCard label="Members in Arrears" value="—" />
      </div>
    </main>
  );
}
