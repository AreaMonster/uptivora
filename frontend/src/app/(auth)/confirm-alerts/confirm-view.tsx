"use client";

import { useEffect, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Alert, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useUrlHash } from "@/lib/use-hash";

type Result = { ok: true; email: string } | { ok: false; message: string };
const attempted = new Set<string>();

export function ConfirmAlerts() {
  const token = useUrlHash();
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!token || attempted.has(token)) return;
    attempted.add(token); // single-use token; dev mode runs effects twice
    api<{ email: string }>("/api/alert-contacts/confirm", { method: "POST", body: { token } }).then(
      (res) => {
        history.replaceState(null, "", window.location.pathname);
        setResult({ ok: true, email: res.email });
      },
      (err: unknown) =>
        setResult({ ok: false, message: err instanceof ApiError ? err.message : "Confirmation failed." }),
    );
  }, [token]);

  const missing = token === "" && !result;
  return (
    <AuthCard title="Monitoring alerts">
      {!result && !missing && <div className="flex justify-center py-6"><Spinner /></div>}
      {result?.ok && (
        <Alert tone="success" title="Confirmed">
          {result.email} will now receive outage and recovery alerts. Every alert email contains a
          one-click unsubscribe link.
        </Alert>
      )}
      {(missing || (result && !result.ok)) && (
        <Alert tone="error">
          {missing ? "This link is incomplete. Open it again from the email." : !result?.ok && result?.message}
        </Alert>
      )}
    </AuthCard>
  );
}
