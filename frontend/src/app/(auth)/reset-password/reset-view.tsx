"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Alert, Button, ButtonLink, TextField } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useUrlHash } from "@/lib/use-hash";

export function ResetPasswordPage() {
  const token = useUrlHash();
  const [password, setPassword] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFieldError(undefined);
    try {
      await api("/api/auth/reset-password", { method: "POST", body: { token, password } });
      history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.fields.password) setFieldError(err.fields.password);
      else setError(err instanceof ApiError ? err.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Choose a new password" subtitle="All your other sessions will be signed out.">
      {done ? (
        <div className="space-y-4">
          <Alert tone="success" title="Password changed">You can now sign in with your new password.</Alert>
          <ButtonLink href="/login" className="w-full">Sign in</ButtonLink>
        </div>
      ) : token === "" ? (
        <Alert tone="error" title="Missing reset token">
          Open the link from the email again, or <Link href="/forgot-password" className="underline">request a new one</Link>.
        </Alert>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error && (
            <Alert tone="error">
              {error} <Link href="/forgot-password" className="underline">Request a new link</Link>
            </Alert>
          )}
          <TextField label="New password" type="password" autoComplete="new-password" required
            minLength={10} value={password} onChange={(e) => setPassword(e.target.value)}
            error={fieldError} hint="At least 10 characters." />
          <Button type="submit" className="w-full" loading={busy} disabled={!token}>Set new password</Button>
        </form>
      )}
    </AuthCard>
  );
}
