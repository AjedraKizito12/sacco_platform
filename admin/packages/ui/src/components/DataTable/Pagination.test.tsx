import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("renders showing range correctly", () => {
    // page=3, pageSize=25, totalRows=130 → first=51, last=75. Values picked
    // to avoid collision with the page-size <select>'s 10/25/50/100 options.
    render(
      <Pagination
        page={3}
        pageSize={25}
        totalRows={130}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    expect(screen.getByText("51")).toBeInTheDocument();
    expect(screen.getByText("75")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
  });

  it("fires onPageChange when next clicked", async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Pagination
        page={1}
        pageSize={25}
        totalRows={120}
        onPageChange={onPageChange}
        onPageSizeChange={() => {}}
      />,
    );
    await user.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("disables prev on first page", () => {
    render(
      <Pagination
        page={1}
        pageSize={25}
        totalRows={120}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });
});
