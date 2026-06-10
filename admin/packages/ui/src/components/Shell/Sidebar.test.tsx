import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LayoutGrid } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { SidebarItem } from "./SidebarItem";

describe("Sidebar", () => {
  it("renders group label + items", () => {
    render(
      <Sidebar
        groups={[
          {
            label: "Platform",
            items: (
              <SidebarItem
                href="/platform/tenants"
                icon={<LayoutGrid size={16} />}
                label="Tenants"
              />
            ),
          },
        ]}
      />,
    );
    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByLabelText("Primary")).toBeInTheDocument();
  });

  it("hides labels when collapsed", () => {
    render(
      <Sidebar
        collapsed
        groups={[
          {
            label: "Platform",
            items: (
              <SidebarItem
                href="/platform/tenants"
                icon={<LayoutGrid size={16} />}
                label="Tenants"
                collapsed
              />
            ),
          },
        ]}
      />,
    );
    expect(screen.queryByText("Tenants")).toBeNull();
    expect(screen.getByLabelText("Tenants")).toBeInTheDocument();
  });

  it("marks active item with aria-current=page", () => {
    render(
      <Sidebar
        groups={[
          {
            items: (
              <SidebarItem
                href="/"
                icon={<LayoutGrid size={16} />}
                label="Dashboard"
                active
              />
            ),
          },
        ]}
      />,
    );
    expect(screen.getByText("Dashboard").closest("a")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
