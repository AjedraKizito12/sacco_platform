import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberSharesTable,
  type MemberShareRow,
} from "./_components/MemberSharesTable";

export const metadata = { title: "Your shares" };

export default async function MemberSharesPage() {
  const { resources } = await getMemberPageContext();
  const res = await resources.member.listShares();
  const rows = (res.data ?? []) as MemberShareRow[];
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Your shares</h1>
      <MemberSharesTable rows={rows} />
    </div>
  );
}
