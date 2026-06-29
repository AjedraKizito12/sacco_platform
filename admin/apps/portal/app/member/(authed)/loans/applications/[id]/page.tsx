import { notFound } from "next/navigation";
import { getMemberPageContext } from "@/auth/server-page-context";
import {
  ApplicationProgress,
  type ApplicationDetail,
} from "./_components/ApplicationProgress";

export const metadata = { title: "Loan application" };

export default async function MemberApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getMemberPageContext();
  const res = (await resources.member.getLoanApplication(id)) as {
    data?: ApplicationDetail;
    error?: unknown;
  };
  if (!res.data) notFound();
  return <ApplicationProgress application={res.data} />;
}
