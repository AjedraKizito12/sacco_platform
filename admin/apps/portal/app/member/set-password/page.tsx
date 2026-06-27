import { ResetPasswordForm } from "@/components/forms/ResetPasswordForm";

// First-time password setup for a member whose operator enabled portal
// access. The backend confirm endpoint is identical to self-service reset,
// so we reuse ResetPasswordForm. The token is read from the `?token=` query
// only (contract F) — never persisted, never logged.
export default function Page() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <ResetPasswordForm variant="member" />
    </main>
  );
}
