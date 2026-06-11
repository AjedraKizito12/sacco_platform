/**
 * Tests for useTableUrlState.
 *
 * nuqs is a direct dependency of @sacco/ui, so NuqsTestingAdapter is available.
 * We use hasMemory=true so that URL updates are persisted across re-renders,
 * matching real browser behaviour.
 */
import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";
import { useTableUrlState } from "./use-table-url-state";

const wrapper = withNuqsTestingAdapter({ hasMemory: true });

describe("useTableUrlState – setFilter resets page", () => {
  it("resets page to 1 when a filter is applied while on page > 1", () => {
    const { result } = renderHook(
      () => useTableUrlState({ filterKeys: ["status"] }),
      { wrapper },
    );

    // Navigate to page 3 first.
    act(() => {
      result.current.setPage(3);
    });
    expect(result.current.page).toBe(3);

    // Applying a filter must reset page to 1.
    act(() => {
      result.current.setFilter("status", "failed");
    });
    expect(result.current.page).toBe(1);
    expect(result.current.filters["status"]).toBe("failed");
  });
});

describe("useTableUrlState – setFilters (batch) resets page", () => {
  it("resets page to 1 when batch filters are applied while on page > 1", () => {
    const { result } = renderHook(
      () => useTableUrlState({ filterKeys: ["status", "type"] }),
      { wrapper },
    );

    // Navigate to page 3 first.
    act(() => {
      result.current.setPage(3);
    });
    expect(result.current.page).toBe(3);

    // Batch-applying filters must also reset page to 1.
    act(() => {
      result.current.setFilters({ status: "failed", type: null });
    });
    expect(result.current.page).toBe(1);
    expect(result.current.filters["status"]).toBe("failed");
  });
});
