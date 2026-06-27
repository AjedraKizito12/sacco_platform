import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberFeesTable,
  type MemberFeeRow,
} from "./_components/MemberFeesTable";

export const metadata = { title: "Your fees" };

export default async function MemberFeesPage() {
  const { resources } = await getMemberPageContext();
  const res = await resources.member.listFees();
  const rows = (res.data ?? []) as MemberFeeRow[];
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Your fees</h1>
      <MemberFeesTable rows={rows} />
    </div>
  );
}
