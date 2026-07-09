import type { ReactNode } from "react";
import { Card, FormattedDate, StatusBadge } from "@sacco/ui";
import type { MemberSelfKycOut } from "@sacco/schemas";
import { getMemberPageContext } from "@/auth/server-page-context";
import { MemberKycSection } from "./_components/MemberKycSection";

export const metadata = { title: "Your profile" };

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function MemberProfilePage() {
  const { member, resources } = await getMemberPageContext();
  const { data: kyc } = await (resources.member.getMyKyc() as Promise<{
    data?: MemberSelfKycOut;
    error?: unknown;
  }>);

  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">
        Your profile
      </h1>
      <Card className="flex max-w-xl flex-col gap-3 p-6">
        <Field label="Full name">{member.full_name}</Field>
        <Field label="Member number">{member.member_number}</Field>
        <Field label="Status">
          <StatusBadge entity="member" status={member.status} />
        </Field>
        <Field label="Email">{member.email ?? "—"}</Field>
        <Field label="Phone">{member.phone ?? "—"}</Field>
        <Field label="Date of birth">
          <FormattedDate value={member.date_of_birth} />
        </Field>
        <Field label="Joined">
          {member.joined_at ? (
            <FormattedDate value={member.joined_at} />
          ) : (
            "—"
          )}
        </Field>
      </Card>

      {kyc ? <MemberKycSection initial={kyc} /> : null}
    </div>
  );
}
