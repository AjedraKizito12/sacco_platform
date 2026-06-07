export default function Home() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <div
        className="w-full rounded-[18px] border border-[var(--color-border-subtle)] bg-[var(--color-surface-elevated)] p-8 shadow-sm"
        style={{ boxShadow: "var(--shadow-sm)" }}
      >
        <p
          className="mb-2 text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--color-text-secondary)" }}
        >
          Portal v1 — sub-plan 03
        </p>
        <h1
          className="mb-3 text-3xl font-bold leading-tight"
          style={{ color: "var(--color-text-primary)" }}
        >
          SACCO Admin Portal
        </h1>
        <p
          className="mb-6 text-base"
          style={{ color: "var(--color-text-secondary)" }}
        >
          Next.js 15 + React 19 bootstrap successful. The auth shell, design
          system, and feature modules land in the sub-plans that follow.
        </p>
        <p className="font-tabular text-sm text-[var(--color-text-secondary)]">
          Bootstrap timestamp: <span suppressHydrationWarning>{new Date().toISOString()}</span>
        </p>
      </div>
    </main>
  );
}
