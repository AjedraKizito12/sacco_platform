import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { NotificationTemplateOut } from "@sacco/schemas";

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

const patchTemplate = vi.fn();
const refresh = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { notifications: { patchTemplate } } }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/notifications/templates",
}));

import { TemplatesTable } from "../_components/TemplatesTable";

const ROWS: NotificationTemplateOut[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    code: "invoice_issued",
    channel: "email",
    locale: "en",
    subject_template: "Invoice {{invoice_number}} issued",
    body_html: null,
    body_text: "Your invoice {{invoice_number}} is ready.",
    sms_body: null,
    variables: { invoice_number: "The invoice number" },
    is_active: true,
    created_at: "2026-07-01T08:00:00Z",
    updated_at: "2026-07-01T08:00:00Z",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    code: "password_reset",
    channel: "in_app",
    locale: "en",
    subject_template: null,
    body_html: null,
    body_text: "A password reset was requested.",
    sms_body: null,
    variables: {},
    is_active: false,
    created_at: "2026-07-01T08:00:00Z",
    updated_at: "2026-07-02T08:00:00Z",
  },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        {children}
      </TenantCurrencyProvider>
    </QueryClientProvider>
  );
}

describe("TemplatesTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    patchTemplate.mockResolvedValue({ data: ROWS[0] });
  });

  it("renders template rows with active state", () => {
    render(<TemplatesTable rows={ROWS} />, { wrapper });
    expect(screen.getByText("invoice_issued")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("edits a template body through the dialog and patches only changed fields", async () => {
    const user = userEvent.setup();
    render(<TemplatesTable rows={ROWS} />, { wrapper });
    await user.click(
      screen.getAllByRole("button", { name: "Edit" })[0] as HTMLElement,
    );
    const bodyText = await screen.findByLabelText("Body (plain text)");
    await user.clear(bodyText);
    await user.type(bodyText, "Updated body");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(patchTemplate).toHaveBeenCalled());
    expect(patchTemplate).toHaveBeenCalledWith(
      "11111111-1111-1111-1111-111111111111",
      { body_text: "Updated body" },
    );
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
