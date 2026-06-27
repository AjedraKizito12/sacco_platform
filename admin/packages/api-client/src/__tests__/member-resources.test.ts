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
});
