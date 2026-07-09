import type { MemberKycRequirementsOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { MemberKycRequirementsForm } from "./_components/MemberKycRequirementsForm";

export const metadata = { title: "Member KYC requirements" };

export default async function MemberKycRequirementsPage() {
  const { resources } = await getTenantPageContext();

  // getKycRequirements is typed Promise<never> (as-never paths); cast to
  // the real { data, error } shape.
  const { data, error } = await (resources.members.getKycRequirements() as Promise<{
    data?: MemberKycRequirementsOut;
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(`Failed to load member KYC requirements: ${JSON.stringify(error)}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Member KYC requirements</h1>
      <MemberKycRequirementsForm initial={data} />
    </div>
  );
}
