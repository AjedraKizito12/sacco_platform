"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, type LoginInput } from "@sacco/schemas";
import { Button, Input, Label, Card } from "@sacco/ui";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useAuthStore } from "@/auth/token-store";

type Variant = "platform" | "tenant" | "member";

interface LoginFormProps {
  variant: Variant;
}

export function LoginForm({ variant }: LoginFormProps) {
  const router = useRouter();
  const params = useSearchParams();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const setAuthContext = useAuthStore((s) => s.setAuthContext);
  const setTenantSlug = useAuthStore((s) => s.setTenantSlug);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const endpoint =
    variant === "platform"
      ? "/api/auth/platform-login"
      : variant === "tenant"
        ? "/api/auth/tenant-login"
        : "/api/auth/member-login";

  async function onSubmit(values: LoginInput) {
    setServerError(null);
    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
      credentials: "include",
    });
    if (!r.ok) {
      const body: unknown = await r.json().catch(() => ({}));
      const detailStr =
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as Record<string, unknown>)["detail"] === "string"
          ? (body as Record<string, unknown>)["detail"]
          : undefined;
      if (
        r.status === 423 ||
        (typeof detailStr === "string" &&
          detailStr.toLowerCase().includes("lock"))
      ) {
        setServerError("Account locked — please try again in 30 minutes.");
      } else if (r.status === 401) {
        setServerError("Invalid email or password.");
      } else {
        setServerError(
          typeof detailStr === "string"
            ? detailStr
            : "Login failed. Please try again.",
        );
      }
      return;
    }
    const data = (await r.json()) as {
      access_token: string;
      tenant_slug?: string;
    };
    setAccessToken(data.access_token);
    setAuthContext(variant);
    if (
      (variant === "tenant" || variant === "member") &&
      data.tenant_slug
    ) {
      setTenantSlug(data.tenant_slug);
    }
    const next = params.get("next");
    const home =
      variant === "platform"
        ? "/platform"
        : variant === "member"
          ? "/member/dashboard"
          : "/";
    router.push(next ?? home);
  }

  return (
    <Card className="max-w-md p-8">
      <h1 className="mb-1 text-[var(--text-h3)] font-semibold text-[var(--text-primary)]">
        {variant === "platform" ? "Platform sign in" : "Sign in"}
      </h1>
      <p className="mb-6 text-[var(--text-body)] text-[var(--text-secondary)]">
        {variant === "platform"
          ? "Sign in to operate the SACCO platform."
          : "Sign in to your SACCO."}
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        <div>
          <Label htmlFor="email" required>
            Email
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            error={Boolean(errors.email)}
            {...register("email")}
          />
          {errors.email && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.email.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="password" required>
            Password
          </Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            error={Boolean(errors.password)}
            {...register("password")}
          />
          {errors.password && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.password.message}
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
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
        <p className="text-center text-sm">
          <a
            href={
              variant === "platform"
                ? "/platform/forgot-password"
                : variant === "member"
                  ? "/member/forgot-password"
                  : "/forgot-password"
            }
            className="text-[var(--text-link)]"
          >
            Forgot password?
          </a>
        </p>
      </form>
    </Card>
  );
}
