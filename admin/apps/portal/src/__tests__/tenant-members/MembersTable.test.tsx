// admin/apps/portal/src/__tests__/tenant-members/MembersTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { MemberOut } from "@sacco/schemas";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1,
      pageSize: 25,
      sortColumn: null,
      sortDirection: "asc" as const,
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/members",
}));

import { MembersTable } from "../../../app/(tenant-authed)/members/_components/MembersTable";

const row: MemberOut = {
  id: "m1",
  member_number: "M-0001",
  full_name: "Ada Loan",
  date_of_birth: "2000-01-01",
  gender: "F",
  phone: "+256700000000",
  email: null,
  physical_address: null,
  national_id_number: null,
  id_document_type: null,
  id_document_number: null,
  id_issued_date: null,
  id_expiry_date: null,
  status: "active",
  joined_at: "2026-06-01",
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

function renderTable(rows: MemberOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MembersTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("MembersTable", () => {
  it("links the member number to the detail page and shows the status badge", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: "M-0001" })).toHaveAttribute(
      "href",
      "/members/m1",
    );
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Ada Loan")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No members yet")).toBeInTheDocument();
  });
});
