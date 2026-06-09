import { ForgotPasswordForm } from "@/components/forms/ForgotPasswordForm";

export default function Page() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <ForgotPasswordForm variant="tenant" />
    </main>
  );
}
