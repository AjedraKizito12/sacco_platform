"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  passwordResetConfirmSchema,
  type PasswordResetConfirmInput,
} from "@sacco/schemas";
import { Button, Card, Input, Label } from "@sacco/ui";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

type Variant = "platform" | "tenant";

interface Props {
  variant: Variant;
}

export function ResetPasswordForm({ variant }: Props) {
  const params = useSearchParams();
  const initialToken = params.get("token") ?? "";
  const [serverError, setServerError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordResetConfirmInput>({
    resolver: zodResolver(passwordResetConfirmSchema),
    defaultValues: {
      token: initialToken,
      new_password: "",
      confirm_password: "",
    },
  });

  async function onSubmit(values: PasswordResetConfirmInput) {
    setServerError(null);
    const r = await fetch(
      variant === "platform"
        ? "/api/auth/platform-reset-password"
        : "/api/auth/tenant-reset-password",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: values.token,
          new_password: values.new_password,
        }),
        credentials: "include",
      },
    );
    if (!r.ok) {
      const body: unknown = await r.json().catch(() => ({}));
      const detailStr =
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as Record<string, unknown>)["detail"] === "string"
          ? (body as Record<string, unknown>)["detail"]
          : undefined;
      setServerError(
        typeof detailStr === "string"
          ? detailStr
          : "Reset failed. The link may have expired.",
      );
      return;
    }
    setSuccess(true);
  }

  if (success) {
    return (
      <Card className="max-w-md p-8">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Password updated
        </h1>
        <p className="mb-4 text-[var(--text-secondary)]">
          Your new password is active. Sign in to continue.
        </p>
        <Link
          href={variant === "platform" ? "/platform/login" : "/login"}
          className="text-[var(--text-link)] hover:underline"
        >
          Back to sign in
        </Link>
      </Card>
    );
  }

  return (
    <Card className="max-w-md p-8">
      <h1 className="mb-1 text-[var(--text-h3)] font-semibold">Set a new password</h1>
      <p className="mb-6 text-[var(--text-secondary)]">
        Choose a password of at least 12 characters.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="token" required>
            Reset token
          </Label>
          <Input id="token" type="text" {...register("token")} />
          {errors.token && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.token.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="new_password" required>
            New password
          </Label>
          <Input
            id="new_password"
            type="password"
            autoComplete="new-password"
            {...register("new_password")}
          />
          {errors.new_password && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.new_password.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="confirm_password" required>
            Confirm password
          </Label>
          <Input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            {...register("confirm_password")}
          />
          {errors.confirm_password && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.confirm_password.message}
            </p>
          )}
        </div>
        {serverError && (
          <p
            role="alert"
            className="rounded-md bg-[var(--status-danger-bg)] p-3 text-sm text-[var(--text-danger)]"
          >
            {serverError}
          </p>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Updating…" : "Update password"}
        </Button>
      </form>
    </Card>
  );
}
