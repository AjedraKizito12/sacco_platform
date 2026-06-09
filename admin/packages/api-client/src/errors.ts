export class UnauthorizedError extends Error {
  constructor(message = "Unauthorized") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

export class SubscriptionPastDueError extends Error {
  detail: string;
  constructor(detail: string) {
    super("Subscription past due — payment required");
    this.name = "SubscriptionPastDueError";
    this.detail = detail;
  }
}

export class SubscriptionSuspendedError extends Error {
  detail: string;
  constructor(detail: string) {
    super("Subscription suspended or cancelled");
    this.name = "SubscriptionSuspendedError";
    this.detail = detail;
  }
}

export class ServerError extends Error {
  status: number;
  requestId: string | null;
  constructor(status: number, requestId: string | null, message?: string) {
    super(message ?? `Server error ${status}`);
    this.name = "ServerError";
    this.status = status;
    this.requestId = requestId;
  }
}
