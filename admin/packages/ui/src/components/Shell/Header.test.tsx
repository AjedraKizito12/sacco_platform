import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "./Header";

describe("Header", () => {
  it("renders logo + provided slots", () => {
    render(
      <Header
        logo={<span>SACCO</span>}
        start={<span>Acme</span>}
        end={<span>menu</span>}
      />,
    );
    expect(screen.getByText("SACCO")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("menu")).toBeInTheDocument();
  });

  it("omits start/center when not provided", () => {
    render(<Header logo={<span>SACCO</span>} />);
    expect(screen.getByText("SACCO")).toBeInTheDocument();
  });
});
