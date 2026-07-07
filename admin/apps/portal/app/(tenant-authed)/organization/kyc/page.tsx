import type { OrganizationKycOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { OrganizationKycScreen } from "./_components/OrganizationKycScreen";

export const metadata = { title: "Organization KYC" };

export default async function OrganizationKycPage() {
  const { resources } = await getTenantPageContext();

  // getKyc is typed Promise<never> (as-never paths); cast to the real
  // { data, error } shape. GET lazily get-or-creates the singleton, so a
  // missing profile is not a 404 — any failure here is a real error.
  const { data, error } = await (resources.organization.getKyc() as Promise<{
    data?: OrganizationKycOut;
    error?: unknown;
  }>);
  if (!data) throw new Error(`Failed to load organization KYC: ${JSON.stringify(error)}`);

  return <OrganizationKycScreen initial={data} />;
}
