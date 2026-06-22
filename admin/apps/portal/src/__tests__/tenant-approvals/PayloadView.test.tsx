import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PayloadView } from "../../../app/(tenant-authed)/approvals/[id]/_components/PayloadView";

describe("PayloadView", () => {
  it("renders payload keys + values and toggles raw JSON", () => {
    render(<PayloadView payload={{ amount: "100.00", confirmed: true, account_id: null }} />);
    expect(screen.getByText("amount")).toBeInTheDocument();
    expect(screen.getByText("100.00")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument(); // boolean true
    expect(screen.getByText("—")).toBeInTheDocument(); // null
    fireEvent.click(screen.getByText("View raw JSON"));
    expect(screen.getByText("Hide raw JSON")).toBeInTheDocument();
  });
});
