// admin/packages/schemas/src/reporting.ts
// Mirror app/modules/reporting/schemas.py. Decimals/dates/datetimes are JSON strings.

export interface ReportRunOut {
  id: string;
  report_type: string;
  as_of_date: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_detail: string | null;
}

export interface TrialBalanceLineOut {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_total: string;
  credit_total: string;
  balance: string;
}
export interface TrialBalanceOut {
  as_of_date: string;
  generated_at: string;
  lines: TrialBalanceLineOut[];
}

export interface LoanPortfolioRowOut {
  loan_id: string;
  loan_reference: string;
  member_id: string;
  product_name: string;
  disbursed_at: string;
  maturity_date: string | null;
  status: string;
  outstanding_principal: string;
  accrued_interest: string;
  total_written_off: string;
  days_in_arrears: number;
  aging_bucket: string;
}
export interface LoanPortfolioOut {
  as_of_date: string;
  generated_at: string;
  rows: LoanPortfolioRowOut[];
}

export interface IncomeStatementLineOut {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_total: string;
  credit_total: string;
  net_movement: string;
}
export interface IncomeStatementOut {
  period_start: string;
  period_end: string;
  generated_at: string;
  lines: IncomeStatementLineOut[];
}

export interface SavingsStatementLineOut {
  savings_account_id: string;
  member_id: string;
  posted_at: string;
  transaction_type: string;
  narration: string | null;
  amount: string;
  running_balance: string;
}
export interface SavingsStatementOut {
  member_id: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  lines: SavingsStatementLineOut[];
}

export interface FeeCollectionRowOut {
  fee_type_id: string;
  fee_type_name: string;
  target_type: string;
  assessed_total: string;
  collected_total: string;
  outstanding_total: string;
  waived_total: string;
}
export interface FeeCollectionReportOut {
  period_start: string;
  period_end: string;
  generated_at: string;
  rows: FeeCollectionRowOut[];
}
