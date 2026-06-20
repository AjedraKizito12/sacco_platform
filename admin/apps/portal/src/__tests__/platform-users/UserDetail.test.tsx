import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PlatformUserOut } from "@sacco/schemas";
import { UserDetail } from "../../../app/platform/(authed)/users/[id]/_components/UserDetail";

const auditBar = <div data-entity-type="platform_user" />;

const user: PlatformUserOut = {
  id: "u1", email: "ada@example.com", full_name: "Ada Ops", is_active: true,
  is_superuser: false, role: "admin", created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z", last_login_at: null,
};

describe("UserDetail", () => {
  it("renders identity fields and an active status", () => {
    render(<UserDetail user={user} canEdit auditBar={auditBar} />);
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Ada Ops")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /edit/i })).toBeInTheDocument();
  });

  it("hides the edit link without permission", () => {
    render(<UserDetail user={user} canEdit={false} auditBar={auditBar} />);
    expect(screen.queryByRole("link", { name: /edit/i })).toBeNull();
  });

  it("renders the audit bar wired to the platform_user entity", () => {
    const { container } = render(<UserDetail user={user} canEdit auditBar={auditBar} />);
    expect(container.querySelector('[data-entity-type="platform_user"]')).not.toBeNull();
  });
});
