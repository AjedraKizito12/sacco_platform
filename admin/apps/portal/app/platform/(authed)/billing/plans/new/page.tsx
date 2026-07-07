import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { PlanForm } from "./_components/PlanForm";

export const metadata = { title: "New Plan" };

export default async function NewPlanPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  return <PlanForm />;
}
