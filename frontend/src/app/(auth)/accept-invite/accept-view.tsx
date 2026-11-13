"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Alert, Button, TextField } from "@/components/ui";
import { ApiError, api, type FieldErrors, type Me, setCsrfToken } from "@/lib/api";
import { useUrlHash } from "@/lib/use-hash";

export function AcceptInvite() {
  const router = useRouter();
  const token = useUrlHash();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    try {
      const me = await api<Me>("/api/auth/accept-invite", {
        method: "POST", body: { token, password, full_name: name },
      });
      setCsrfToken(me.csrf_token);
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) setFields(err.fields);
      else setError(err instanceof ApiError ? err.message : "Could not accept the invitation.");
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Join your team on Uptivora" subtitle="Choose a password to activate your account."
      footer={<Link href="/login" className="link">Already activated? Sign in</Link>}>
      {token === "" ? (
        <Alert tone="error">This invitation link is incomplete. Open it again from the email.</Alert>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error && <Alert tone="error">{error}</Alert>}
          <TextField label="Your name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          <TextField label="Password" type="password" autoComplete="new-password" required minLength={10}
            value={password} onChange={(e) => setPassword(e.target.value)} error={fields.password}
            hint="At least 10 characters." />
          <Button type="submit" className="w-full" loading={busy} disabled={!token}>Activate account</Button>
        </form>
      )}
    </AuthCard>
  );
}
