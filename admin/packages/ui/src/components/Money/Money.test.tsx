import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Money } from "./Money";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

describe("Money", () => {
  it("formats UGX with no decimals", () => {
    render(<Money amount="1234567" currency="UGX" />);
    expect(screen.getByText("UGX 1,234,567")).toBeInTheDocument();
  });

  it("formats USD with 2 decimals", () => {
    render(<Money amount="50" currency="USD" />);
    expect(screen.getByText("USD 50.00")).toBeInTheDocument();
  });

  it("renders zero correctly", () => {
    render(<Money amount="0" currency="UGX" />);
    expect(screen.getByText("UGX 0")).toBeInTheDocument();
  });

  it("renders negative with danger colour", () => {
    render(<Money amount="-1234" currency="UGX" />);
    const span = screen.getByText("-UGX 1,234");
    expect(span.className).toMatch(/text-\[var\(--text-danger\)\]/);
  });

  it("uses the provider's currency when no prop", () => {
    render(
      <TenantCurrencyProvider currency="KES">
        <Money amount="50" />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText("KES 50.00")).toBeInTheDocument();
  });

  it("does not crash on invalid input", () => {
    render(<Money amount="not-a-number" currency="UGX" />);
    expect(screen.getByText(/UGX/)).toBeInTheDocument();
  });

  it("emits data-currency and data-amount for downstream tools", () => {
    render(<Money amount="42" currency="USD" />);
    const span = screen.getByText(/USD/);
    expect(span).toHaveAttribute("data-currency", "USD");
    expect(span).toHaveAttribute("data-amount", "42");
  });
});
