"use client";

import {
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
  UnauthorizedError,
} from "@sacco/api-client";
import { useRouter } from "next/navigation";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { PermissionDeniedError } from "@/auth/permissions";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches the four typed errors that can bubble out of any render and routes
 * to the matching system page. Other errors bubble to Next.js's default
 * error UI.
 */
export class AppErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Sub-plan 40 (Sentry) wires the real reporter. Until then, just log.
    // eslint-disable-next-line no-console
    console.error("AppErrorBoundary caught:", error, info);
  }

  override componentDidUpdate(_prev: Props, prev: State): void {
    if (prev.error === this.state.error) return;
    const e = this.state.error;
    if (!e) return;
    if (e instanceof SubscriptionPastDueError) {
      window.location.assign("/subscription-past-due");
    } else if (e instanceof SubscriptionSuspendedError) {
      window.location.assign("/account-suspended");
    } else if (e instanceof PermissionDeniedError) {
      window.location.assign("/permission-denied");
    } else if (e instanceof UnauthorizedError) {
      window.location.assign("/login");
    }
  }

  override render(): ReactNode {
    if (this.state.error) return null;
    return this.props.children;
  }
}

/** Hook variant for hooks-only consumers. */
export function useErrorRedirect(error: unknown): void {
  const router = useRouter();
  if (!error) return;
  if (error instanceof SubscriptionPastDueError) {
    router.push("/subscription-past-due");
  } else if (error instanceof SubscriptionSuspendedError) {
    router.push("/account-suspended");
  } else if (error instanceof PermissionDeniedError) {
    router.push("/permission-denied");
  } else if (error instanceof UnauthorizedError) {
    router.push("/login");
  }
}
