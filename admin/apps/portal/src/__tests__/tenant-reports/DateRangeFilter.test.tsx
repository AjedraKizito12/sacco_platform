// admin/apps/portal/src/__tests__/tenant-reports/DateRangeFilter.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

import { DateRangeFilter } from "../../../app/(tenant-authed)/reports/income-statement/_components/DateRangeFilter";

describe("DateRangeFilter", () => {
  beforeEach(() => vi.clearAllMocks());

  it("pushes from_date and to_date on Apply", async () => {
    render(<DateRangeFilter basePath="/reports/income-statement" />);
    await userEvent.type(screen.getByLabelText(/from/i), "2026-01-01");
    await userEvent.type(screen.getByLabelText(/to/i), "2026-06-30");
    await userEvent.click(screen.getByRole("button", { name: /apply/i }));
    expect(push).toHaveBeenCalledTimes(1);
    const target = push.mock.calls[0]![0] as string;
    expect(target).toContain("/reports/income-statement?");
    expect(target).toContain("from_date=2026-01-01");
    expect(target).toContain("to_date=2026-06-30");
  });
});
