// admin/apps/portal/app/(tenant-authed)/credit/products/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, Money, Percentage } from "@sacco/ui";
import type { LoanProductOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { EditProductForm } from "./_components/EditProductForm";

export const metadata = { title: "Loan product" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function LoanProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data: product } = await (resources.credit.getProduct(id) as Promise<{
    data?: LoanProductOut;
    error?: unknown;
  }>);
  if (!product) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">{product.name}</h1>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Terms</h2>
        <Row label="Interest method">{product.interest_method}</Row>
        <Row label="Annual interest rate">
          <Percentage value={product.annual_interest_rate} />
        </Row>
        <Row label="Repayment frequency">{product.repayment_frequency}</Row>
        <Row label="Max term (periods)">{product.max_term_periods}</Row>
        <Row label="Amount range">
          <Money amount={product.min_amount} /> – <Money amount={product.max_amount} />
        </Row>
        <Row label="Required approvals">{product.required_approvals}</Row>
        <Row label="Repayment allocation">{product.repayment_allocation}</Row>
        <Row label="Disbursement destinations">
          {product.disbursement_destinations.join(", ")}
        </Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">GL mapping</h2>
        <Row label="Principal receivable">{product.gl_principal_receivable_code}</Row>
        <Row label="Interest receivable">{product.gl_interest_receivable_code}</Row>
        <Row label="Interest income">{product.gl_interest_income_code}</Row>
        <Row label="Loan-loss expense">{product.gl_loan_loss_expense_code ?? "—"}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Risk</h2>
        <Row label="Penalty fee type">{product.penalty_fee_type_code ?? "—"}</Row>
        <Row label="Write-off threshold">
          <Money amount={product.write_off_threshold} />
        </Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Meta</h2>
        <Row label="Active">{product.is_active ? "Yes" : "No"}</Row>
        <Row label="Created"><FormattedDateTime value={product.created_at} /></Row>
        <Row label="Updated"><FormattedDateTime value={product.updated_at} /></Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Edit</h2>
        <EditProductForm product={product} />
      </Card>
    </div>
  );
}
