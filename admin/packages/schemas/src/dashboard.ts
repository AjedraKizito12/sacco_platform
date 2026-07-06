// Mirrors app/modules/dashboard/schemas.py TenantDashboardStatsOut.
// Decimal fields arrive as JSON strings (FastAPI serialises Decimal as a
// string) — the same shape <Money> reads. Single-currency per tenant (UGX),
// rendered via <TenantCurrencyProvider>.
export interface TenantDashboardStatsOut {
  members: Record<string, number>;
  total_members: number;
  total_savings: string;
  loans_outstanding_principal: string;
  loans_by_status: Record<string, number>;
  members_in_arrears: number;
  approvals_pending: number;
  applications_pending: number;
  last_updated: string;
}
