/**
 * Flat factory object. Convention: each domain has a `root` (so a single
 * mutation can invalidate `["tenants"]` and blow away every cached tenant
 * query) plus per-operation factories that produce stable keys.
 *
 * Filters are stringified positionally so `["tenants", "list", {status: "active"}]`
 * differs from `["tenants", "list", {}]`.
 */
export const queryKeys = {
  platformAuth: {
    me: () => ["platformAuth", "me"] as const,
  },
  platformUsers: {
    root: () => ["platformUsers"] as const,
    list: () => ["platformUsers", "list"] as const,
    detail: (id: string) => ["platformUsers", "detail", id] as const,
  },
  tenants: {
    root: () => ["tenants"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["tenants", "list", filters ?? {}] as const,
    detail: (id: string) => ["tenants", "detail", id] as const,
    users: (id: string) => ["tenants", "users", id] as const,
  },
  billing: {
    root: () => ["billing"] as const,
    plans: (filters?: Record<string, unknown>) =>
      ["billing", "plans", filters ?? {}] as const,
    plan: (id: string) => ["billing", "plan", id] as const,
    subscriptions: (filters?: Record<string, unknown>) =>
      ["billing", "subscriptions", filters ?? {}] as const,
    subscription: (id: string) => ["billing", "subscription", id] as const,
    invoices: (filters?: Record<string, unknown>) =>
      ["billing", "invoices", filters ?? {}] as const,
    invoice: (id: string) => ["billing", "invoice", id] as const,
    pendingPayments: () => ["billing", "pendingPayments"] as const,
  },
  members: {
    root: () => ["members"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["members", "list", filters ?? {}] as const,
    detail: (id: string) => ["members", "detail", id] as const,
  },
  savings: {
    root: () => ["savings"] as const,
    products: () => ["savings", "products"] as const,
    accounts: (filters?: Record<string, unknown>) =>
      ["savings", "accounts", filters ?? {}] as const,
    account: (id: string) => ["savings", "account", id] as const,
    transactions: (id: string) =>
      ["savings", "account", id, "transactions"] as const,
  },
  credit: {
    root: () => ["credit"] as const,
    products: () => ["credit", "products"] as const,
    applications: (filters?: Record<string, unknown>) =>
      ["credit", "applications", filters ?? {}] as const,
    application: (id: string) => ["credit", "application", id] as const,
    loans: (filters?: Record<string, unknown>) =>
      ["credit", "loans", filters ?? {}] as const,
    loan: (id: string) => ["credit", "loan", id] as const,
    schedule: (id: string) => ["credit", "loan", id, "schedule"] as const,
    repayments: (id: string) => ["credit", "loan", id, "repayments"] as const,
    payrollBatches: () => ["credit", "payrollBatches"] as const,
  },
  fees: {
    root: () => ["fees"] as const,
    types: () => ["fees", "types"] as const,
    assessments: (filters?: Record<string, unknown>) =>
      ["fees", "assessments", filters ?? {}] as const,
  },
  ledger: {
    root: () => ["ledger"] as const,
    accounts: () => ["ledger", "accounts"] as const,
    account: (id: string) => ["ledger", "account", id] as const,
    journalEntries: () => ["ledger", "journalEntries"] as const,
  },
  reporting: {
    root: () => ["reporting"] as const,
    trialBalance: (params?: Record<string, unknown>) =>
      ["reporting", "trial-balance", params ?? {}] as const,
    loanPortfolio: (params?: Record<string, unknown>) =>
      ["reporting", "loan-portfolio", params ?? {}] as const,
    incomeStatement: (params?: Record<string, unknown>) =>
      ["reporting", "income-statement", params ?? {}] as const,
    savingsStatement: (params?: Record<string, unknown>) =>
      ["reporting", "savings-statement", params ?? {}] as const,
    feeCollection: (params?: Record<string, unknown>) =>
      ["reporting", "fee-collection", params ?? {}] as const,
    runs: () => ["reporting", "runs"] as const,
  },
  approvals: {
    root: () => ["approvals"] as const,
    platform: (filters?: Record<string, unknown>) =>
      ["approvals", "platform", filters ?? {}] as const,
    tenant: (filters?: Record<string, unknown>) =>
      ["approvals", "tenant", filters ?? {}] as const,
    detail: (id: string) => ["approvals", "detail", id] as const,
  },
  impersonations: {
    root: () => ["impersonations"] as const,
    active: () => ["impersonations", "active"] as const,
    all: () => ["impersonations", "all"] as const,
  },
  audit: {
    root: () => ["audit"] as const,
    platform: (filters?: Record<string, unknown>) =>
      ["audit", "platform", filters ?? {}] as const,
    tenant: (filters?: Record<string, unknown>) =>
      ["audit", "tenant", filters ?? {}] as const,
    detail: (id: string) => ["audit", "detail", id] as const,
  },
  keys: {
    root: () => ["keys"] as const,
    list: () => ["keys", "list"] as const,
  },
  admin: {
    dashboardStats: () => ["admin", "dashboardStats"] as const,
  },
  member: {
    root: () => ["member"] as const,
    savings: () => ["member", "savings"] as const,
    savingsTransactions: (id: string) =>
      ["member", "savings", id, "transactions"] as const,
    shares: () => ["member", "shares"] as const,
    loans: () => ["member", "loans"] as const,
    loan: (id: string) => ["member", "loan", id] as const,
    loanSchedule: (id: string) => ["member", "loan", id, "schedule"] as const,
    loanStatement: (id: string) => ["member", "loan", id, "statement"] as const,
    fees: () => ["member", "fees"] as const,
  },
} as const;
