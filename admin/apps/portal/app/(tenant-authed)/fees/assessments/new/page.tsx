// admin/apps/portal/app/(tenant-authed)/fees/assessments/new/page.tsx
import type {
  LoanOut,
  MemberOut,
  SavingsAccountOut,
  ShareAccountListItemOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import {
  CreateAssessmentForm,
  type FeeTypeOption,
  type TargetMap,
} from "./_components/CreateAssessmentForm";

export const metadata = { title: "New fee assessment" };

export default async function NewFeeAssessmentPage() {
  const { resources } = await getTenantPageContext();
  const [
    { data: types },
    { data: members },
    { data: loans },
    { data: savings },
    { data: shares },
  ] = await Promise.all([
    resources.fees.listTypes({}) as Promise<{ data?: FeeTypeOption[]; error?: unknown }>,
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
    resources.credit.listLoans({}) as Promise<{ data?: LoanOut[]; error?: unknown }>,
    resources.savings.listAccounts({}) as Promise<{ data?: SavingsAccountOut[]; error?: unknown }>,
    resources.shares.listAccounts({}) as Promise<{
      data?: ShareAccountListItemOut[];
      error?: unknown;
    }>,
  ]);

  const memberById = new Map((members ?? []).map((m) => [m.id, m]));
  const ml = (memberId: string) => {
    const m = memberById.get(memberId);
    return m ? `${m.full_name} (${m.member_number})` : memberId;
  };

  const targets: TargetMap = {
    member: (members ?? []).map((m) => ({
      id: m.id,
      label: `${m.full_name} (${m.member_number})`,
    })),
    loan: (loans ?? []).map((l) => ({
      id: l.id,
      label: `${l.loan_reference} · ${ml(l.member_id)}`,
    })),
    savings_account: (savings ?? []).map((s) => ({
      id: s.id,
      label: `${s.product_name} · ${ml(s.member_id)}`,
    })),
    share_account: (shares ?? []).map((s) => ({
      id: s.id,
      label: `${s.product_name} · ${ml(s.member_id)}`,
    })),
  };

  const feeTypeOptions: FeeTypeOption[] = (types ?? []).map((t) => ({
    id: t.id,
    code: t.code,
    name: t.name,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New fee assessment</h1>
      <CreateAssessmentForm feeTypes={feeTypeOptions} targets={targets} />
    </div>
  );
}
