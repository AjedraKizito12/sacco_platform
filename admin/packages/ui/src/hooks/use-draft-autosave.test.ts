import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useDraftAutoSave } from "./use-draft-autosave";

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useDraftAutoSave", () => {
  it("persists after the debounce window", () => {
    const { result, rerender } = renderHook(
      ({ values }: { values: { name: string } }) =>
        useDraftAutoSave({ formKey: "loan-app", values }),
      { initialProps: { values: { name: "Mary" } } },
    );

    rerender({ values: { name: "Mary Akello" } });

    // Before the debounce fires, nothing is saved.
    expect(window.localStorage.getItem("sacco_draft:loan-app")).toBeNull();

    act(() => {
      vi.advanceTimersByTime(750);
    });

    const raw = window.localStorage.getItem("sacco_draft:loan-app");
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw!).values).toEqual({ name: "Mary Akello" });
    expect(result.current.lastSavedAt).toBeTruthy();
  });

  it("restore() returns the persisted values", () => {
    window.localStorage.setItem(
      "sacco_draft:loan-app",
      JSON.stringify({ values: { name: "Sarah" }, savedAt: "x" }),
    );
    const { result } = renderHook(() =>
      useDraftAutoSave({ formKey: "loan-app", values: { name: "" } }),
    );
    expect(result.current.restore()).toEqual({ name: "Sarah" });
  });

  it("clear() removes the saved draft", () => {
    window.localStorage.setItem(
      "sacco_draft:loan-app",
      JSON.stringify({ values: { name: "Sarah" }, savedAt: "x" }),
    );
    const { result } = renderHook(() =>
      useDraftAutoSave({ formKey: "loan-app", values: { name: "" } }),
    );
    act(() => {
      result.current.clear();
    });
    expect(window.localStorage.getItem("sacco_draft:loan-app")).toBeNull();
  });

  it("respects enabled=false (no writes)", () => {
    const { rerender } = renderHook(
      ({ values, enabled }: { values: { name: string }; enabled: boolean }) =>
        useDraftAutoSave({ formKey: "loan-app", values, enabled }),
      { initialProps: { values: { name: "X" }, enabled: false } },
    );
    rerender({ values: { name: "Y" }, enabled: false });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(window.localStorage.getItem("sacco_draft:loan-app")).toBeNull();
  });
});
