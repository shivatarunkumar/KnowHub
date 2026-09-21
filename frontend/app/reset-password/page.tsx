import { Suspense } from "react";
import { ResetPasswordForm } from "@/components/PasswordResetForms";

export const metadata = { title: "Choose a new password · KnowHub" };

export default function ResetPasswordPage() {
  // ResetPasswordForm reads ?token= with useSearchParams, which Next requires to sit
  // inside a Suspense boundary so the rest of the route can still be prerendered.
  return (
    <Suspense fallback={<div className="mx-auto max-w-sm px-4 py-12 text-sm text-muted">Loading…</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
