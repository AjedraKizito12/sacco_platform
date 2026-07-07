// admin/apps/portal/app/(tenant-authed)/shares/accounts/new/page.tsx
import type { MemberOut, ShareProductOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import {
  OpenAccountForm,
  type MemberOption,
  type ProductOption,
} from "./_components/OpenAccountForm";

export const metadata = { title: "Open share account" };

export default async function NewShareAccountPage({
  searchParams,
}: {
  searchParams: Promise<{ member_id?: string }>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();
  const [{ data: members }, { data: products }] = await Promise.all([
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
    resources.shares.listProducts({}) as Promise<{
      data?: ShareProductOut[];
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
    <OpenAccountForm
      members={memberOptions}
      products={productOptions}
      {...(sp.member_id ? { defaultMemberId: sp.member_id } : {})}
    />
  );
}
