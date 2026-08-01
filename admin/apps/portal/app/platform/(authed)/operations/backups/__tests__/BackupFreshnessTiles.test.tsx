import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BackupFreshnessTiles } from "../_components/BackupFreshnessTiles";

describe("BackupFreshnessTiles", () => {
  it("flags a stale backup and stale verify", () => {
    render(
      <BackupFreshnessTiles
        lastBackupAt="2026-07-01T00:00:00Z"
        lastVerifiedAt="2026-07-01T00:00:00Z"
        now={Date.parse("2026-07-12T00:00:00Z")}
      />,
    );
    expect(screen.getAllByTestId("tile-stale")).toHaveLength(2);
  });

  it("shows fresh tiles for recent timestamps", () => {
    const now = Date.parse("2026-07-12T12:00:00Z");
    render(
      <BackupFreshnessTiles
        lastBackupAt="2026-07-12T06:00:00Z"
        lastVerifiedAt="2026-07-10T06:00:00Z"
        now={now}
      />,
    );
    expect(screen.getAllByTestId("tile-fresh")).toHaveLength(2);
    expect(screen.queryByTestId("tile-stale")).toBeNull();
  });

  it("treats null timestamps as stale and renders Never", () => {
    render(<BackupFreshnessTiles lastBackupAt={null} lastVerifiedAt={null} />);
    expect(screen.getAllByTestId("tile-stale")).toHaveLength(2);
    expect(screen.getAllByText("Never")).toHaveLength(2);
  });
});
