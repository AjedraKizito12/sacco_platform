import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";

describe("Button", () => {
  it("renders with an accessible name from children", () => {
    render(<Button>Save member</Button>);
    expect(screen.getByRole("button", { name: "Save member" })).toBeInTheDocument();
  });

  it("fires onClick when clicked", async () => {
    const user = userEvent.setup();
    let clicks = 0;
    render(<Button onClick={() => (clicks += 1)}>Click</Button>);
    await user.click(screen.getByRole("button"));
    expect(clicks).toBe(1);
  });

  it("respects the disabled prop", async () => {
    const user = userEvent.setup();
    let clicks = 0;
    render(
      <Button disabled onClick={() => (clicks += 1)}>
        Cannot click
      </Button>,
    );
    await user.click(screen.getByRole("button"));
    expect(clicks).toBe(0);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("renders as a child element when asChild is true", () => {
    render(
      <Button asChild>
        <a href="/members">Go to members</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Go to members" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/members");
  });
});
