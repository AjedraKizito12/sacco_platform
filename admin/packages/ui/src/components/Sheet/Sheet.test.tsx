import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sheet, SheetContent, SheetTrigger } from "./Sheet";

describe("Sheet", () => {
  it("opens on trigger click", async () => {
    const user = userEvent.setup();
    render(
      <Sheet>
        <SheetTrigger>Open</SheetTrigger>
        <SheetContent aria-label="audit details">Audit log</SheetContent>
      </Sheet>,
    );
    await user.click(screen.getByText("Open"));
    expect(await screen.findByRole("dialog", { name: "audit details" })).toBeInTheDocument();
  });
});
