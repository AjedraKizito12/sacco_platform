import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

import { JwtKeysTable } from "../../../app/platform/(authed)/settings/security/_components/JwtKeysTable";
import type { JwtKeyOut } from "@sacco/schemas";

const rows: JwtKeyOut[] = [
  {
    id: "k1",
    kid: "key-2026-06",
    algorithm: "RS256",
    audience: "platform",
    status: "active",
    created_at: "2026-06-01T00:00:00Z",
    activated_at: "2026-06-01T00:00:00Z",
    retired_at: null,
    deleted_at: null,
  },
];

describe("JwtKeysTable", () => {
  it("renders a key row with kid, status badge, and algorithm", () => {
    render(<JwtKeysTable rows={rows} />);
    expect(screen.getByText("key-2026-06")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("RS256")).toBeInTheDocument();
  });

  it("shows the empty state when there are no keys", () => {
    render(<JwtKeysTable rows={[]} />);
    expect(screen.getByText("No signing keys")).toBeInTheDocument();
  });
});
