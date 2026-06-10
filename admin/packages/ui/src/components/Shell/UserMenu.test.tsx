import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UserMenu } from "./UserMenu";

describe("UserMenu", () => {
  it("renders the initials button", () => {
    render(
      <UserMenu
        fullName="Jane Operator"
        email="jane@platform.example"
        onSignOut={() => {}}
      />,
    );
    const trigger = screen.getByLabelText("User menu for Jane Operator");
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent("JO");
  });

  it("invokes onSignOut from the menu", async () => {
    const onSignOut = vi.fn();
    render(
      <UserMenu
        fullName="Jane Operator"
        email="jane@platform.example"
        onSignOut={onSignOut}
      />,
    );
    await userEvent.click(screen.getByLabelText("User menu for Jane Operator"));
    await userEvent.click(await screen.findByText("Sign out"));
    expect(onSignOut).toHaveBeenCalledOnce();
  });

  it("renders the contextLabel when supplied", async () => {
    render(
      <UserMenu
        fullName="Jane Operator"
        email="jane@platform.example"
        contextLabel="Superuser"
        onSignOut={() => {}}
      />,
    );
    await userEvent.click(screen.getByLabelText("User menu for Jane Operator"));
    expect(await screen.findByText("Superuser")).toBeInTheDocument();
  });
});
