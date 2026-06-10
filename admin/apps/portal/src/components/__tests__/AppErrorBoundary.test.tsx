import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { render } from "@testing-library/react";
import {
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
  UnauthorizedError,
} from "@sacco/api-client";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { PermissionDeniedError } from "@/auth/permissions";

let originalLocation: Location;
let assignMock: ReturnType<typeof vi.fn>;
let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  originalLocation = window.location;
  assignMock = vi.fn();
  Object.defineProperty(window, "location", {
    value: { ...originalLocation, assign: assignMock },
    writable: true,
    configurable: true,
  });
  // React logs the boundary catch to console.error — silence in tests.
  consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    value: originalLocation,
    writable: true,
    configurable: true,
  });
  consoleErrorSpy.mockRestore();
});

function Bomb({ throwable }: { throwable: Error }): null {
  throw throwable;
}

describe("AppErrorBoundary", () => {
  it("redirects to /subscription-past-due on 402 error", () => {
    render(
      <AppErrorBoundary>
        <Bomb throwable={new SubscriptionPastDueError("expired")} />
      </AppErrorBoundary>,
    );
    expect(assignMock).toHaveBeenCalledWith("/subscription-past-due");
  });

  it("redirects to /account-suspended on gate 403", () => {
    render(
      <AppErrorBoundary>
        <Bomb throwable={new SubscriptionSuspendedError("suspended")} />
      </AppErrorBoundary>,
    );
    expect(assignMock).toHaveBeenCalledWith("/account-suspended");
  });

  it("redirects to /permission-denied on PermissionDeniedError", () => {
    render(
      <AppErrorBoundary>
        <Bomb throwable={new PermissionDeniedError("billing.write")} />
      </AppErrorBoundary>,
    );
    expect(assignMock).toHaveBeenCalledWith("/permission-denied");
  });

  it("redirects to /login on UnauthorizedError", () => {
    render(
      <AppErrorBoundary>
        <Bomb throwable={new UnauthorizedError()} />
      </AppErrorBoundary>,
    );
    expect(assignMock).toHaveBeenCalledWith("/login");
  });
});
