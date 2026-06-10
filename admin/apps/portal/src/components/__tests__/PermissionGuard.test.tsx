import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PermissionGuard } from "@/auth/PermissionGuard";
import { useCurrentUserStore } from "@/auth/use-current-user";

afterEach(() => {
  useCurrentUserStore.getState().setUser(null);
});

describe("PermissionGuard", () => {
  it("hides children when user lacks permission", () => {
    useCurrentUserStore.getState().setUser({
      id: "u1",
      email: "t@test.example",
      full_name: "T",
      is_active: true,
      is_superuser: false,
      role: "support",
    });
    render(
      <PermissionGuard permission="billing.write">
        <button>Edit plan</button>
      </PermissionGuard>,
    );
    expect(screen.queryByText("Edit plan")).toBeNull();
  });

  it("renders children when user has rank", () => {
    useCurrentUserStore.getState().setUser({
      id: "u2",
      email: "a@test.example",
      full_name: "A",
      is_active: true,
      is_superuser: false,
      role: "admin",
    });
    render(
      <PermissionGuard permission="billing.write">
        <button>Edit plan</button>
      </PermissionGuard>,
    );
    expect(screen.getByText("Edit plan")).toBeInTheDocument();
  });

  it("renders fallback when user lacks permission", () => {
    useCurrentUserStore.getState().setUser({
      id: "u3",
      email: "x@test.example",
      full_name: "X",
      is_active: true,
      is_superuser: false,
      role: "support",
    });
    render(
      <PermissionGuard
        permission="billing.write"
        fallback={<span>Read-only</span>}
      >
        <button>Edit plan</button>
      </PermissionGuard>,
    );
    expect(screen.getByText("Read-only")).toBeInTheDocument();
  });

  it("denies a null user", () => {
    render(
      <PermissionGuard permission="billing.read">
        <button>See bills</button>
      </PermissionGuard>,
    );
    expect(screen.queryByText("See bills")).toBeNull();
  });
});
