import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MoneyInput } from "./MoneyInput";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

function Controlled({
  initial = "",
  currency,
  allowNegative,
}: {
  initial?: string;
  currency?: string;
  allowNegative?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <div>
      <MoneyInput
        value={value}
        onValueChange={setValue}
        {...(currency !== undefined ? { currency } : {})}
        {...(allowNegative !== undefined ? { allowNegative } : {})}
        aria-label="amount"
      />
      <p data-testid="state">{value}</p>
    </div>
  );
}

describe("MoneyInput", () => {
  it("shows the currency chip from the provider when no prop", () => {
    render(
      <TenantCurrencyProvider currency="KES">
        <Controlled />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText("KES")).toBeInTheDocument();
  });

  it("formats with thousands separators as the user types", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="UGX" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "1234567");
    expect(input.value).toBe("1,234,567");
    expect(screen.getByTestId("state").textContent).toBe("1234567");
  });

  it("canonicalises on blur — UGX → no decimals", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="UGX" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "12");
    await user.tab();
    expect(input.value).toBe("12");
    expect(screen.getByTestId("state").textContent).toBe("12");
  });

  it("canonicalises on blur — USD → 2 decimals", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="USD" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "12");
    await user.tab();
    expect(input.value).toBe("12.00");
    expect(screen.getByTestId("state").textContent).toBe("12.00");
  });

  it("blocks the minus sign by default", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="USD" />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "-50");
    expect(input.value).toBe("50");
  });

  it("permits negative when allowNegative", async () => {
    const user = userEvent.setup();
    render(<Controlled currency="USD" allowNegative />);
    const input = screen.getByLabelText("amount") as HTMLInputElement;
    await user.type(input, "-50");
    expect(input.value).toBe("-50");
  });

  it("calls onBlur passthrough", async () => {
    const onBlur = vi.fn();
    const user = userEvent.setup();
    function H() {
      const [v, set] = useState("");
      return (
        <MoneyInput
          value={v}
          onValueChange={set}
          currency="USD"
          aria-label="amount"
          onBlur={onBlur}
        />
      );
    }
    render(<H />);
    await user.type(screen.getByLabelText("amount"), "1");
    await user.tab();
    expect(onBlur).toHaveBeenCalled();
  });
});
