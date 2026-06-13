import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ImpersonationBanner } from "./ImpersonationBanner";

describe("ImpersonationBanner", () => {
  it("names the tenant and renders an End now action", () => {
    render(
      <ImpersonationBanner
        tenantName="Alpha SACCO"
        expiresAt="2026-06-13T12:30:00Z"
        onEnd={() => {}}
      />,
    );
    expect(screen.getByText(/impersonating/i)).toBeInTheDocument();
    expect(screen.getByText(/alpha sacco/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /end now/i })).toBeInTheDocument();
  });

  it("calls onEnd when End now is clicked", async () => {
    const onEnd = vi.fn();
    render(
      <ImpersonationBanner tenantName="Alpha SACCO" expiresAt="2026-06-13T12:30:00Z" onEnd={onEnd} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /end now/i }));
    expect(onEnd).toHaveBeenCalledOnce();
  });

  it("disables End now while busy", () => {
    render(
      <ImpersonationBanner tenantName="Alpha SACCO" expiresAt="2026-06-13T12:30:00Z" onEnd={() => {}} busy />,
    );
    expect(screen.getByRole("button", { name: /end now/i })).toBeDisabled();
  });

  it("exposes the banner as a status region for assistive tech", () => {
    render(
      <ImpersonationBanner tenantName="Alpha SACCO" expiresAt="2026-06-13T12:30:00Z" onEnd={() => {}} />,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
