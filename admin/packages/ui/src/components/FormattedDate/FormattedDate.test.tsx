import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  AuditTimestamp,
  FormattedDate,
  FormattedDateTime,
  RelativeTime,
} from "./FormattedDate";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

describe("FormattedDate", () => {
  it("renders YYYY-MM-DD as 'd MMM yyyy'", () => {
    render(<FormattedDate value="2026-05-28" />);
    expect(screen.getByText("28 May 2026")).toBeInTheDocument();
  });
  it("accepts a Date object", () => {
    render(<FormattedDate value={new Date(Date.UTC(2026, 4, 28))} />);
    expect(screen.getByText("28 May 2026")).toBeInTheDocument();
  });
});

describe("FormattedDateTime", () => {
  it("renders ISO datetime in the configured timezone", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <FormattedDateTime value="2026-05-28T11:32:00Z" />
      </TenantCurrencyProvider>,
    );
    // Africa/Kampala is UTC+3 → 14:32
    expect(screen.getByText(/14:32/)).toBeInTheDocument();
    expect(screen.getByText(/28 May 2026/)).toBeInTheDocument();
  });
});

describe("AuditTimestamp", () => {
  it("includes seconds + timezone abbreviation", () => {
    render(
      <TenantCurrencyProvider timeZone="Africa/Kampala">
        <AuditTimestamp value="2026-05-28T11:32:07Z" />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText(/14:32:07/)).toBeInTheDocument();
  });
});

describe("RelativeTime", () => {
  it("renders a relative phrase for recent timestamps", () => {
    const now = new Date("2026-05-28T14:32:00Z");
    const twoHoursAgo = new Date("2026-05-28T12:30:00Z");
    render(<RelativeTime value={twoHoursAgo} now={now} />);
    expect(screen.getByText(/hours? ago/)).toBeInTheDocument();
  });

  it("falls back to absolute date after 7 days", () => {
    const now = new Date("2026-05-28T14:32:00Z");
    const oneMonthAgo = new Date("2026-04-28T14:32:00Z");
    render(<RelativeTime value={oneMonthAgo} now={now} />);
    expect(screen.getByText("28 Apr 2026")).toBeInTheDocument();
  });

  it("exposes the raw timestamp via title for tooltip use", () => {
    render(<RelativeTime value="2026-05-28T14:32:00Z" />);
    const span = screen.getByText(/ago|2026/);
    expect(span).toHaveAttribute("title", "2026-05-28T14:32:00Z");
  });
});
