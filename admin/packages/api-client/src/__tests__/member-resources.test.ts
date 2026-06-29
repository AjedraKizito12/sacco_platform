import { describe, it, expect, vi } from "vitest";
import { member } from "../resources/member";

describe("member resource", () => {
  it("listSavings hits /member/savings", () => {
    const api = { GET: vi.fn(), POST: vi.fn() } as never;
    member(api as never).listSavings();
    expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
      "/member/savings",
      expect.anything(),
    );
  });

  it("getLoanStatement hits the statement path", () => {
    const api = { GET: vi.fn(), POST: vi.fn() } as never;
    member(api as never).getLoanStatement("loan-1");
    expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
      "/member/loans/{loan_id}/statement",
      expect.anything(),
    );
  });

  it("listLoanApplications hits /member/loan-applications", () => {
    const api = { GET: vi.fn() } as never;
    member(api).listLoanApplications();
    expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
      "/member/loan-applications",
      expect.anything(),
    );
  });

  it("getLoanApplication hits /member/loan-applications/{application_id}", () => {
    const api = { GET: vi.fn() } as never;
    member(api).getLoanApplication("abc");
    expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
      "/member/loan-applications/{application_id}",
      expect.objectContaining({
        params: { path: { application_id: "abc" } },
      }),
    );
  });
});
