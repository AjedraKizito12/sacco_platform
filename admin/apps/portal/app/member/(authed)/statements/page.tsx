import { StatementForm } from "./_components/StatementForm";

export const metadata = { title: "Statements" };

export default function MemberStatementsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Statements</h1>
      <StatementForm />
    </div>
  );
}
