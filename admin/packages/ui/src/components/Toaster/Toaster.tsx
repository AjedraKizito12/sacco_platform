"use client";

import { Toaster as SonnerToaster, toast } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      closeButton
      toastOptions={{
        className: "font-sans",
        style: {
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--border-subtle)",
        },
      }}
    />
  );
}

export { toast };
