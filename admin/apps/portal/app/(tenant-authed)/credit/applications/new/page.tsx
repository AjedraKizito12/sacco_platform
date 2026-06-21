// admin/apps/portal/app/(tenant-authed)/credit/applications/new/page.tsx
import type { LoanProductOut, MemberOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import {
  CreateApplicationForm,
  type MemberOption,
  type ProductOption,
} from "./_components/CreateApplicationForm";

export const metadata = { title: "New loan application" };

export default async function NewLoanApplicationPage({
  searchParams,
}: {
  searchParams: Promise<{ member_id?: string }>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();
  const [{ data: members }, { data: products }] = await Promise.all([
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
    resources.credit.listProducts({}) as Promise<{
      data?: LoanProductOut[];
      error?: unknown;
    }>,
  ]);

  const memberOptions: MemberOption[] = (members ?? []).map((m) => ({
    id: m.id,
    full_name: m.full_name,
    member_number: m.member_number,
  }));
  const productOptions: ProductOption[] = (products ?? []).map((p) => ({
    id: p.id,
    name: p.name,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New loan application</h1>
      <CreateApplicationForm
        members={memberOptions}
        products={productOptions}
        {...(sp.member_id ? { defaultMemberId: sp.member_id } : {})}
      />
    </div>
  );
}
