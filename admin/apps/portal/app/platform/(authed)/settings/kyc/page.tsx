import type { SaccoKycRequirementsOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { SaccoKycRequirementsForm } from "./_components/SaccoKycRequirementsForm";

export const metadata = { title: "SACCO KYC requirements" };

export default async function SaccoKycSettingsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  // getSaccoRequirements is typed Promise<never> (as-never paths); cast to
  // the real { data, error } shape.
  const { data, error } = await (resources.kyc.getSaccoRequirements() as Promise<{
    data?: SaccoKycRequirementsOut;
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(`Failed to load SACCO KYC requirements: ${JSON.stringify(error)}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">SACCO KYC requirements</h1>
      <SaccoKycRequirementsForm initial={data} />
    </div>
  );
}
