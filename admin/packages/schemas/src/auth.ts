// admin/packages/schemas/src/auth.ts
import { z } from "zod";

// Backend-aligned: min length 12 (auth_password_min_length default in Settings).
// The IAM layer is authoritative; if config diverges, the API rejects with 401.
const passwordMinLength = 12;

export const loginSchema = z.object({
  email: z.string().trim().toLowerCase().email("Must be a valid email"),
  password: z.string().min(1, "Password is required"),
});

export const refreshSchema = z.object({
  refresh_token: z.string().min(10),
});

export const passwordResetRequestSchema = z.object({
  email: z.string().trim().toLowerCase().email("Must be a valid email"),
});

export const passwordResetConfirmSchema = z
  .object({
    token: z.string().min(10, "Reset token is required"),
    new_password: z
      .string()
      .min(
        passwordMinLength,
        `Password must be at least ${passwordMinLength} characters`,
      ),
    confirm_password: z.string(),
  })
  .refine(
    (data) => data.new_password === data.confirm_password,
    {
      message: "Passwords do not match",
      path: ["confirm_password"],
    },
  );

export type LoginInput = z.infer<typeof loginSchema>;
export type RefreshInput = z.infer<typeof refreshSchema>;
export type PasswordResetRequestInput = z.infer<typeof passwordResetRequestSchema>;
export type PasswordResetConfirmInput = z.infer<typeof passwordResetConfirmSchema>;
