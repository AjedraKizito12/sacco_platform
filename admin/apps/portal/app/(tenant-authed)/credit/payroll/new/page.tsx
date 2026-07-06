// admin/apps/portal/app/(tenant-authed)/credit/payroll/new/page.tsx
import type { MemberOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import {
  CreatePayrollBatchForm,
  type GlAccountOption,
  type MemberOption,
} from "./_components/CreatePayrollBatchForm";

export const metadata = { title: "New payroll batch" };

export default async function NewPayrollBatchPage() {
  const { resources } = await getTenantPageContext();
  const [{ data: members }, { data: accounts }] = await Promise.all([
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
    resources.ledger.listAccounts({}) as Promise<{
      data?: GlAccountOption[];
      error?: unknown;
    }>,
  ]);

  const memberOptions: MemberOption[] = (members ?? []).map((m) => ({
    id: m.id,
    full_name: m.full_name,
    member_number: m.member_number,
  }));

  return <CreatePayrollBatchForm members={memberOptions} glAccounts={accounts ?? []} />;
}
