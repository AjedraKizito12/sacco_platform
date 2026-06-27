import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberSavingsTable,
  type MemberSavingsRow,
} from "./_components/MemberSavingsTable";

export const metadata = { title: "Your savings" };

export default async function MemberSavingsPage() {
  const { resources } = await getMemberPageContext();
  const res = await resources.member.listSavings();
  const rows = (res.data ?? []) as MemberSavingsRow[];
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">
        Your savings
      </h1>
      <MemberSavingsTable rows={rows} />
    </div>
  );
}
