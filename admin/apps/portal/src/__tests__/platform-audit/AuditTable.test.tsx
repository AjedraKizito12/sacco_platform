import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1,
      pageSize: 25,
      sortColumn: "occurred_at",
      sortDirection: "desc" as const,
      filters: {},
      density: "default" as const,
      setPage: vi.fn(),
      setPageSize: vi.fn(),
      setSort: vi.fn(),
      setFilter: vi.fn(),
      setFilters: vi.fn(),
      setDensity: vi.fn(),
      reset: vi.fn(),
    }),
  };
});

import { AuditTable } from "../../components/audit/AuditTable";
import type { AuditEntryOut } from "@sacco/schemas";

const rows: AuditEntryOut[] = [
  {
    id: "a1",
    table_name: "tenants",
    record_id: "r1",
    operation: "update",
    actor_type: "platform_user",
    actor_id: "u1",
    actor_label: "op@test",
    before_state: { x: 1 },
    after_state: { x: 2 },
    occurred_at: "2026-06-20T10:00:00Z",
    request_id: null,
    impersonation_id: null,
  },
];

describe("AuditTable", () => {
  it("renders a row with table, operation, and actor", () => {
    render(<AuditTable items={rows} total={1} showImpersonation={false} />);
    expect(screen.getByText("tenants")).toBeInTheDocument();
    expect(screen.getByText("update")).toBeInTheDocument();
    expect(screen.getByText("op@test")).toBeInTheDocument();
  });

  it("shows the empty state when no rows", () => {
    render(<AuditTable items={[]} total={0} showImpersonation={false} />);
    expect(screen.getByText("No audit entries")).toBeInTheDocument();
  });
});
