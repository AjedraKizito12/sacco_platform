// admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/page.tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, StatusBadge } from "@sacco/ui";
import { MEMBER_KYC_FIELDS, type KycSubmissionDetailOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { KycReviewActions } from "./_components/KycReviewActions";

export const metadata = { title: "KYC submission" };

export default async function KycSubmissionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.members.getKycSubmission(id) as Promise<{
    data?: KycSubmissionDetailOut;
    error?: unknown;
  }>);
  if (!data) notFound();

  const { submission, current, member_number, full_name } = data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[var(--text-h3)] font-semibold">
            KYC submission — {full_name}
          </h1>
          <p className="text-[var(--text-secondary)]">
            <Link
              href={`/members/${submission.member_id}`}
              className="text-[var(--text-link)]"
            >
              {member_number}
            </Link>{" "}
            · Submitted <FormattedDateTime value={submission.submitted_at} />
          </p>
        </div>
        <StatusBadge entity="kyc_submission" status={submission.status} />
      </div>

      {submission.status === "rejected" && submission.rejection_reason ? (
        <Card className="p-4">
          <p className="font-medium">Rejection reason</p>
          <p className="text-[var(--text-secondary)]">{submission.rejection_reason}</p>
        </Card>
      ) : null}

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-[var(--border-default)]">
              <th className="p-3 font-medium">Field</th>
              <th className="p-3 font-medium">Current</th>
              <th className="p-3 font-medium">Proposed</th>
            </tr>
          </thead>
          <tbody>
            {MEMBER_KYC_FIELDS.map((field) => {
              const before = current[field.key];
              const after = submission.proposed[field.key];
              const changed = before !== after;
              return (
                <tr
                  key={field.key}
                  className="border-b border-[var(--border-default)] last:border-0"
                >
                  <td className="p-3 text-[var(--text-secondary)]">{field.label}</td>
                  <td className="p-3">{before ?? "—"}</td>
                  <td className={changed ? "p-3 font-medium" : "p-3"}>{after ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <KycReviewActions submissionId={submission.id} status={submission.status} />
    </div>
  );
}
