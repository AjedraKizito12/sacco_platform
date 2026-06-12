// admin/apps/portal/src/__tests__/platform-tenants/NewTenantWizard.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const create = vi.fn();
const get = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { create, get } } }),
}));

import { NewTenantWizard } from "../../../app/platform/(authed)/tenants/new/_components/NewTenantWizard";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t9", slug: "kampala-teachers", schema_name: "tenant_kampala_teachers",
    name: "Kampala Teachers", status: "provisioning", is_active: false,
    provisioning_state: "create_schema", failed_step: null, failure_reason: null,
    provisioning_started_at: "2026-06-11T00:00:00Z", provisioning_completed_at: null,
    seed_version: 1, created_at: "2026-06-11T00:00:00Z", updated_at: "2026-06-11T00:00:00Z",
    ...over,
  };
}

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NewTenantWizard />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("NewTenantWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("auto-suggests the slug from the name until the slug is edited", async () => {
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    expect(screen.getByLabelText(/slug/i)).toHaveValue("kampala-teachers");
    await userEvent.clear(screen.getByLabelText(/slug/i));
    await userEvent.type(screen.getByLabelText(/slug/i), "kt-sacco");
    await userEvent.type(screen.getByLabelText(/^name/i), " Extra");
    expect(screen.getByLabelText(/slug/i)).toHaveValue("kt-sacco");
  });

  it("stops auto-suggesting once the slug is touched, even after clearing it", async () => {
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    expect(screen.getByLabelText(/slug/i)).toHaveValue("kampala-teachers");
    await userEvent.clear(screen.getByLabelText(/slug/i)); // touches slug, then empties it
    await userEvent.type(screen.getByLabelText(/^name/i), " Extra");
    expect(screen.getByLabelText(/slug/i)).toHaveValue(""); // not re-suggested
  });

  it("rejects an invalid slug before submitting", async () => {
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "X");
    await userEvent.clear(screen.getByLabelText(/slug/i));
    await userEvent.type(screen.getByLabelText(/slug/i), "Bad Slug!");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    expect(await screen.findByText(/lowercase letters, digits and hyphens/i)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("submits, then shows live provisioning progress until active", async () => {
    create.mockResolvedValue({
      data: { tenant: tenant({}), status_url: "/platform/tenants/t9" },
      error: undefined,
    });
    get.mockResolvedValue({ data: tenant({ status: "active", provisioning_state: null }), error: undefined });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        slug: "kampala-teachers",
        name: "Kampala Teachers",
      }),
    );
    expect(await screen.findByText(/tenant is ready/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view tenant/i })).toHaveAttribute(
      "href",
      "/platform/tenants/t9",
    );
  });

  it("shows the failure panel when provisioning fails", async () => {
    create.mockResolvedValue({
      data: { tenant: tenant({}), status_url: "/platform/tenants/t9" },
      error: undefined,
    });
    get.mockResolvedValue({
      data: tenant({ status: "failed", failed_step: "run_migrations", failure_reason: "alembic timeout" }),
      error: undefined,
    });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    expect(await screen.findByText(/provisioning failed/i)).toBeInTheDocument();
    expect(screen.getByText(/alembic timeout/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open tenant/i })).toBeInTheDocument();
  });

  it("includes admin_email in the payload when provided", async () => {
    create.mockResolvedValue({
      data: { tenant: tenant({}), status_url: "/platform/tenants/t9" },
      error: undefined,
    });
    get.mockResolvedValue({ data: tenant({ status: "active", provisioning_state: null }), error: undefined });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.type(screen.getByLabelText(/initial admin email/i), "admin@example.com");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        slug: "kampala-teachers",
        name: "Kampala Teachers",
        admin_email: "admin@example.com",
      }),
    );
  });

  it("surfaces a duplicate-slug error and stays on the form", async () => {
    create.mockResolvedValue({
      data: undefined,
      error: { detail: "Tenant slug 'kampala-teachers' already exists" },
    });
    renderWizard();
    await userEvent.type(screen.getByLabelText(/^name/i), "Kampala Teachers");
    await userEvent.click(screen.getByRole("button", { name: /provision tenant/i }));
    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/slug/i)).toBeInTheDocument();
  });
});
