"use client";

import { useEffect, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Alert, ButtonLink, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useUrlHash } from "@/lib/use-hash";

type Result = { ok: true } | { ok: false; message: string };
const attempted = new Set<string>();

export function VerifyEmailPage() {
  const token = useUrlHash();
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!token || attempted.has(token)) return;
    attempted.add(token); // React dev mode runs effects twice; tokens are single-use
    api("/api/auth/verify-email", { method: "POST", body: { token } }).then(
      () => {
        history.replaceState(null, "", window.location.pathname);
        setResult({ ok: true });
      },
      (err: unknown) =>
        setResult({ ok: false, message: err instanceof ApiError ? err.message : "Verification failed." }),
    );
  }, [token]);

  const missing = token === "" && !result;
  return (
    <AuthCard title="Confirm your email">
      {!result && !missing && <div className="flex justify-center py-6"><Spinner /></div>}
      {result?.ok && (
        <div className="space-y-4">
          <Alert tone="success" title="Email confirmed">Alerts will now be delivered to this address.</Alert>
          <ButtonLink href="/dashboard" className="w-full">Go to dashboard</ButtonLink>
        </div>
      )}
      {(missing || (result && !result.ok)) && (
        <div className="space-y-4">
          <Alert tone="error">
            {missing ? "This link is incomplete. Open it again from the email." : !result?.ok && result?.message}
          </Alert>
          <p className="text-sm text-fg-muted">You can request a new confirmation email from your dashboard.</p>
          <ButtonLink href="/dashboard" variant="secondary" className="w-full">Go to dashboard</ButtonLink>
        </div>
      )}
    </AuthCard>
  );
}
