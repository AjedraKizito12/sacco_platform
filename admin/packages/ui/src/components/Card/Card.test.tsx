import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Card, CardHeader, CardBody, KpiCard } from "./Card";

describe("Card", () => {
  it("renders children", () => {
    render(<Card>hello</Card>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
  it("supports header + body composition", () => {
    render(
      <Card>
        <CardHeader>Header</CardHeader>
        <CardBody>Body</CardBody>
      </Card>,
    );
    expect(screen.getByText("Header")).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });
});

describe("KpiCard", () => {
  it("renders label, value, trend", () => {
    render(
      <KpiCard
        label="Total Members"
        value="1,234"
        trend={{ direction: "up", label: "+5.2% MoM" }}
      />,
    );
    expect(screen.getByText("Total Members")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
    expect(screen.getByText("+5.2% MoM")).toBeInTheDocument();
  });
});
