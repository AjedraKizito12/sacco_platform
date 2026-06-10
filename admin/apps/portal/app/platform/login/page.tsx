import { LoginForm } from "@/components/forms/LoginForm";

export default function PlatformLogin() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <LoginForm variant="platform" />
    </main>
  );
}
