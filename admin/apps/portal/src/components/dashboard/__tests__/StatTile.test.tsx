import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Users } from "lucide-react";
import { StatTile } from "../StatTile";

describe("StatTile", () => {
  it("renders a positive delta chip with a leading plus", () => {
    render(
      <StatTile label="Savings" icon={<Users size={18} />} delta={12.4} deltaLabel="vs last month">
        1,000
      </StatTile>,
    );
    expect(screen.getByText("+12.4%")).toBeInTheDocument();
    expect(screen.getByText("vs last month")).toBeInTheDocument();
  });

  it("renders a negative delta chip", () => {
    render(
      <StatTile label="Savings" icon={<Users size={18} />} delta={-8}>
        1,000
      </StatTile>,
    );
    expect(screen.getByText("-8.0%")).toBeInTheDocument();
  });

  it("renders no delta chip when delta is null", () => {
    render(
      <StatTile label="Savings" icon={<Users size={18} />} delta={null}>
        1,000
      </StatTile>,
    );
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
  });
});
