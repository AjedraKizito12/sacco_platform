import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberLoansTable,
  type MemberLoanRow,
} from "./_components/MemberLoansTable";
import {
  MemberApplicationsTable,
  type MemberApplicationRow,
} from "./_components/MemberApplicationsTable";

export const metadata = { title: "Your loans" };

export default async function MemberLoansPage() {
  const { resources } = await getMemberPageContext();
  const [loansRes, appsRes] = await Promise.all([
    resources.member.listLoans(),
    resources.member.listLoanApplications(),
  ]);
  const loanRows = (loansRes.data ?? []) as MemberLoanRow[];
  const appRows = (appsRes.data ?? []) as MemberApplicationRow[];
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h1 className="text-[length:var(--text-h4)] font-semibold">Your loans</h1>
        <MemberLoansTable rows={loanRows} />
      </section>
      <section className="space-y-4">
        <h2 className="text-[length:var(--text-h4)] font-semibold">
          Loan applications
        </h2>
        <MemberApplicationsTable rows={appRows} />
      </section>
    </div>
  );
}
