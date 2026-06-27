import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberLoansTable,
  type MemberLoanRow,
} from "./_components/MemberLoansTable";

export const metadata = { title: "Your loans" };

export default async function MemberLoansPage() {
  const { resources } = await getMemberPageContext();
  const res = await resources.member.listLoans();
  const rows = (res.data ?? []) as MemberLoanRow[];
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Your loans</h1>
      <MemberLoansTable rows={rows} />
    </div>
  );
}
