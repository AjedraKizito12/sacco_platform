// admin/apps/portal/app/(tenant-authed)/members/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDate, StatusBadge } from "@sacco/ui";
import type {
  LoanOut,
  MemberOut,
  SavingsAccountOut,
  ShareAccountListItemOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ChangeMemberStatusButton } from "./_components/ChangeMemberStatusButton";
import { MemberSavingsSection } from "./_components/MemberSavingsSection";
import { MemberSharesSection } from "./_components/MemberSharesSection";
import { MemberLoansSection } from "./_components/MemberLoansSection";

export const metadata = { title: "Member" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

function dash(value: string | null): ReactNode {
  return value && value.length > 0 ? value : "—";
}

function dateOrDash(value: string | null): ReactNode {
  return value ? <FormattedDate value={value} /> : "—";
}

export default async function MemberDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const [{ data }, { data: accounts }, { data: shareAccounts }, { data: loans }] =
    await Promise.all([
      resources.members.get(id) as Promise<{ data?: MemberOut; error?: unknown }>,
      resources.savings.listAccounts({ member_id: id }) as Promise<{
        data?: SavingsAccountOut[];
        error?: unknown;
      }>,
      resources.shares.listAccounts({ member_id: id }) as Promise<{
        data?: ShareAccountListItemOut[];
        error?: unknown;
      }>,
      resources.credit.listLoans({ member_id: id }) as Promise<{
        data?: LoanOut[];
        error?: unknown;
      }>,
    ]);
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-[var(--text-h3)] font-semibold">{data.full_name}</h1>
          <span className="text-[var(--text-secondary)]">{data.member_number}</span>
        </div>
        <ChangeMemberStatusButton memberId={data.id} currentStatus={data.status} />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Identity</h2>
        <Row label="Member #">{data.member_number}</Row>
        <Row label="Full name">{data.full_name}</Row>
        <Row label="Date of birth">{dateOrDash(data.date_of_birth)}</Row>
        <Row label="Gender">{data.gender}</Row>
        <Row label="Status">
          <StatusBadge entity="member" status={data.status} />
        </Row>
        <Row label="Joined">{dateOrDash(data.joined_at)}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Contact</h2>
        <Row label="Phone">{dash(data.phone)}</Row>
        <Row label="Email">{dash(data.email)}</Row>
        <Row label="Physical address">{dash(data.physical_address)}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">KYC</h2>
        <Row label="National ID number">{dash(data.national_id_number)}</Row>
        <Row label="ID document type">{dash(data.id_document_type)}</Row>
        <Row label="ID document number">{dash(data.id_document_number)}</Row>
        <Row label="ID issued">{dateOrDash(data.id_issued_date)}</Row>
        <Row label="ID expiry">{dateOrDash(data.id_expiry_date)}</Row>
      </Card>

      <MemberSavingsSection memberId={data.id} accounts={accounts ?? []} />
      <MemberSharesSection memberId={data.id} accounts={shareAccounts ?? []} />
      <MemberLoansSection loans={loans ?? []} />
    </div>
  );
}
