import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  CommandPalette,
  type CommandPaletteItem,
  type CommandPaletteProps,
} from "./CommandPalette";

const items: CommandPaletteItem[] = [
  { id: "1", title: "Grace N", subtitle: "M-0001", url: "/members/1", group: "Members" },
  { id: "2", title: "John O", subtitle: "M-0002", url: "/members/2", group: "Members" },
];

function setup(overrides: Partial<CommandPaletteProps> = {}) {
  const onQueryChange = vi.fn();
  const onSelect = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <CommandPalette
      open
      onOpenChange={onOpenChange}
      query="gr"
      onQueryChange={onQueryChange}
      items={items}
      onSelect={onSelect}
      {...overrides}
    />,
  );
  return { onQueryChange, onSelect, onOpenChange };
}

describe("CommandPalette", () => {
  it("renders items grouped by group", () => {
    setup();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("Grace N")).toBeInTheDocument();
    expect(screen.getByText("John O")).toBeInTheDocument();
  });

  it("calls onQueryChange as the user types", async () => {
    const user = userEvent.setup();
    const { onQueryChange } = setup();
    await user.type(screen.getByRole("textbox"), "a");
    expect(onQueryChange).toHaveBeenCalled();
  });

  it("Enter selects the active (first) item", async () => {
    const user = userEvent.setup();
    const { onSelect } = setup();
    await user.type(screen.getByRole("textbox"), "{Enter}");
    expect(onSelect).toHaveBeenCalledWith(items[0]);
  });

  it("ArrowDown moves the active item, then Enter selects it", async () => {
    const user = userEvent.setup();
    const { onSelect } = setup();
    await user.type(screen.getByRole("textbox"), "{ArrowDown}{Enter}");
    expect(onSelect).toHaveBeenCalledWith(items[1]);
  });

  it("shows the empty label when query is set and there are no items", () => {
    setup({ items: [], emptyLabel: "No matches" });
    expect(screen.getByText("No matches")).toBeInTheDocument();
  });

  it("renders a StatusBadge for an item with status + statusEntity", () => {
    setup({
      items: [
        {
          id: "L1",
          title: "L-0001",
          subtitle: "loan",
          url: "/credit/loans/L1",
          group: "Loans",
          status: "disbursed",
          statusEntity: "loan",
        },
      ],
    });
    // loan/disbursed maps to the "Disbursed" badge label.
    expect(screen.getByText("Disbursed")).toBeInTheDocument();
  });

  it("renders a nav-action item (no status) and selects it", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const navItem: CommandPaletteItem = {
      id: "nav-billing",
      title: "Go to Billing",
      subtitle: "",
      url: "/platform/billing",
      group: "Navigate",
    };
    render(
      <CommandPalette
        open
        onOpenChange={() => {}}
        query="bill"
        onQueryChange={() => {}}
        items={[navItem]}
        onSelect={onSelect}
      />,
    );
    expect(screen.getByText("Navigate")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "{Enter}");
    expect(onSelect).toHaveBeenCalledWith(navItem);
  });
});
