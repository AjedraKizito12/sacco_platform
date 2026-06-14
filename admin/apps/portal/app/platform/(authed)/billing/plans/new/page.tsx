import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { PlanForm } from "./_components/PlanForm";

export const metadata = { title: "New Plan" };

export default async function NewPlanPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New plan</h1>
      <PlanForm />
    </div>
  );
}
