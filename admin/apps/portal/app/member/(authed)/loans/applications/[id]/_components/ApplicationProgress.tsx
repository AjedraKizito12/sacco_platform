"use client";

import { Card, Money, StatusBadge, Stepper, type StepperStep } from "@sacco/ui";

export interface ApplicationDetail {
  id: string;
  status: string;
  requested_amount: string;
  requested_term_periods: number;
  approved_amount: string | null;
  approved_term_periods: number | null;
  rejection_reason: string | null;
  reviewed_at: string | null;
  decided_at: string | null;
}

const STEPS: StepperStep[] = [
  { id: "submitted", label: "Submitted" },
  { id: "under_review", label: "Under review" },
  { id: "approved", label: "Approved" },
  { id: "disbursed", label: "Disbursed" },
];

// Map the application status onto the linear stepper. Terminal non-linear
// states (rejected / withdrawn / cancelled) are handled separately below.
const STEP_FOR_STATUS: Record<string, string> = {
  draft: "submitted",
  submitted: "submitted",
  under_review: "under_review",
  approved: "approved",
  disbursed: "disbursed",
};

const TERMINAL_NEGATIVE = new Set(["rejected", "withdrawn", "cancelled"]);

export function ApplicationProgress({
  application,
}: {
  application: ApplicationDetail;
}) {
  const isNegative = TERMINAL_NEGATIVE.has(application.status);
  const currentStepId = STEP_FOR_STATUS[application.status] ?? "submitted";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-[length:var(--text-h4)] font-semibold">
          Loan application
        </h1>
        <StatusBadge entity="loan_application" status={application.status} />
      </div>

      {isNegative ? (
        <Card className="flex flex-col gap-2 p-6">
          <p className="text-[14px] font-medium text-[var(--text-primary)]">
            This application is {application.status}.
          </p>
          {application.rejection_reason ? (
            <p className="text-[13px] text-[var(--text-secondary)]">
              {application.rejection_reason}
            </p>
          ) : null}
        </Card>
      ) : (
        <Card className="p-6">
          <Stepper steps={STEPS} currentStepId={currentStepId} />
        </Card>
      )}

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex justify-between">
          <span className="text-[13px] text-[var(--text-tertiary)]">Requested</span>
          <span className="text-[14px]">
            <Money amount={application.requested_amount} /> ·{" "}
            {application.requested_term_periods} periods
          </span>
        </div>
        {application.approved_amount ? (
          <div className="flex justify-between">
            <span className="text-[13px] text-[var(--text-tertiary)]">Approved</span>
            <span className="text-[14px]">
              <Money amount={application.approved_amount} /> ·{" "}
              {application.approved_term_periods} periods
            </span>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
