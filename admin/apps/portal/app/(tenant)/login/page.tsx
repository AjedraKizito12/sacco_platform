import { LoginForm } from "@/components/forms/LoginForm";

export default function TenantLogin() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <LoginForm variant="tenant" />
    </main>
  );
}
