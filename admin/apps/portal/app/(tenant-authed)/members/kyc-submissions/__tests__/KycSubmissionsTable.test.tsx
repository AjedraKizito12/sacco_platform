// admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/__tests__/KycSubmissionsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { KycSubmissionListItemOut } from "@sacco/schemas";

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
  usePathname: () => "/members/kyc-submissions",
}));

import { KycSubmissionsTable } from "../_components/KycSubmissionsTable";

const ROWS: KycSubmissionListItemOut[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    member_id: "m1",
    member_number: "M-00001",
    full_name: "Jane Doe",
    status: "pending",
    submitted_at: "2026-07-08T10:00:00Z",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    member_id: "m2",
    member_number: "M-00002",
    full_name: "John Ouma",
    status: "rejected",
    submitted_at: "2026-07-07T10:00:00Z",
  },
];

function renderTable(rows: KycSubmissionListItemOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <KycSubmissionsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("KycSubmissionsTable", () => {
  it("renders member numbers linking to the submission detail", () => {
    renderTable(ROWS);
    const link = screen.getByRole("link", { name: "M-00001" });
    expect(link).toHaveAttribute(
      "href",
      "/members/kyc-submissions/11111111-1111-1111-1111-111111111111",
    );
  });

  it("renders submission statuses through StatusBadge", () => {
    renderTable(ROWS);
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No KYC submissions")).toBeInTheDocument();
  });
});
