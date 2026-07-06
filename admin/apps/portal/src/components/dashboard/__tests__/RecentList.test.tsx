import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecentList } from "../RecentList";

describe("RecentList", () => {
  it("renders a row per item with primary, secondary and trailing content", () => {
    render(
      <RecentList
        items={[
          {
            id: "1",
            primary: "Sarah Nakato",
            secondary: "M-0001",
            trailing: "UGX 500",
            href: "/members/1",
          },
          { id: "2", primary: "David Okello", secondary: "M-0002" },
        ]}
      />,
    );
    expect(screen.getByText("Sarah Nakato")).toBeInTheDocument();
    expect(screen.getByText("M-0001")).toBeInTheDocument();
    expect(screen.getByText("UGX 500")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sarah Nakato/ })).toHaveAttribute(
      "href",
      "/members/1",
    );
  });

  it("renders the empty state when there are no items", () => {
    render(<RecentList items={[]} emptyLabel="No recent members" />);
    expect(screen.getByText("No recent members")).toBeInTheDocument();
  });
});
