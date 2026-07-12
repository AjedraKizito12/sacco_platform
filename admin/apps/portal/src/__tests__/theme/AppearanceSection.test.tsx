import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { AppearanceSection } from "@/components/theme/AppearanceSection";

function renderSection() {
  return render(
    <ThemeProvider initial={{ mode: "light", accent: "default", fontSize: "default" }}>
      <AppearanceSection />
    </ThemeProvider>,
  );
}

describe("AppearanceSection", () => {
  it("shows the initial selection and applies a new accent on click", async () => {
    const user = userEvent.setup();
    renderSection();

    // Initial selection: light mode is pressed.
    expect(screen.getByRole("button", { name: "Light" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(document.documentElement.hasAttribute("data-accent")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Blue" }));

    expect(screen.getByRole("button", { name: "Blue" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(document.documentElement.getAttribute("data-accent")).toBe("blue");
  });
});
