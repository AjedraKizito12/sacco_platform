import type { FetchClient } from "../client";

export function ledger(api: FetchClient) {
  return {
    listAccounts: (query?: Record<string, unknown>) =>
      api.GET("/ledger/accounts" as never, { params: { query } } as never),
    createAccount: (body: Record<string, unknown>) =>
      api.POST("/ledger/accounts" as never, { body } as never),
    getAccount: (id: string) =>
      api.GET("/ledger/accounts/{account_id}" as never, {
        params: { path: { account_id: id } },
      } as never),
    listJournalEntries: (query?: Record<string, unknown>) =>
      api.GET("/ledger/journal-entries" as never, { params: { query } } as never),
    getJournalEntry: (id: string) =>
      api.GET("/ledger/journal-entries/{entry_id}" as never, {
        params: { path: { entry_id: id } },
      } as never),
    submitJournalEntry: (body: Record<string, unknown>) =>
      api.POST("/ledger/journal-entries/submit" as never, { body } as never),
  } as const;
}
