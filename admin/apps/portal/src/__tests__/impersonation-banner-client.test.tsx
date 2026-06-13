import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const assign = vi.fn();
const fetchMock = vi.fn();

import { ImpersonationBannerClient } from "../../app/(tenant-authed)/_components/ImpersonationBannerClient";

describe("ImpersonationBannerClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("location", { assign } as unknown as Location);
  });

  it("ends the session and returns to the tenant detail in platform context", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    render(
      <ImpersonationBannerClient
        impersonationId="imp1"
        tenantId="t1"
        tenantName="Alpha SACCO"
        expiresAt="2026-06-13T12:30:00Z"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /end now/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/impersonation/end",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/platform/tenants/t1"));
  });
});
