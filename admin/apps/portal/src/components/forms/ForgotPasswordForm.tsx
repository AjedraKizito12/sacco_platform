"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  passwordResetRequestSchema,
  type PasswordResetRequestInput,
} from "@sacco/schemas";
import { Button, Card, Input, Label } from "@sacco/ui";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";

type Variant = "platform" | "tenant";

interface Props {
  variant: Variant;
}

export function ForgotPasswordForm({ variant }: Props) {
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordResetRequestInput>({
    resolver: zodResolver(passwordResetRequestSchema),
    defaultValues: { email: "" },
  });

  async function onSubmit(values: PasswordResetRequestInput) {
    // Anti-enumeration: backend always returns 204. We surface a success
    // state regardless of whether the email exists.
    await fetch(
      variant === "platform"
        ? "/api/auth/platform-forgot-password"
        : "/api/auth/tenant-forgot-password",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
        credentials: "include",
      },
    ).catch(() => {});
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <Card className="max-w-md p-8">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">Check your email</h1>
        <p className="text-[var(--text-secondary)]">
          If an account exists for the address you entered, reset instructions
          will arrive shortly. Reset tokens expire after 15 minutes.
        </p>
        <p className="mt-4">
          <Link
            href={variant === "platform" ? "/platform/login" : "/login"}
            className="text-[var(--text-link)] hover:underline"
          >
            Back to sign in
          </Link>
        </p>
      </Card>
    );
  }

  return (
    <Card className="max-w-md p-8">
      <h1 className="mb-1 text-[var(--text-h3)] font-semibold">Reset password</h1>
      <p className="mb-6 text-[var(--text-secondary)]">
        We&apos;ll send instructions to the address you provide.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="email" required>
            Email
          </Label>
          <Input id="email" type="email" autoComplete="email" {...register("email")} />
          {errors.email && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.email.message}
            </p>
          )}
        </div>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Sending…" : "Send reset instructions"}
        </Button>
      </form>
    </Card>
  );
}
