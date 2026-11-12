"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Alert, Button, Spinner, TextField } from "@/components/ui";
import { ApiError, api, type FieldErrors, type Me, type PublicConfig, setCsrfToken } from "@/lib/api";

export function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<PublicConfig>("/api/public/config").then(setConfig).catch(() => setConfig(null));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    try {
      const me = await api<Me>("/api/auth/register", { method: "POST", body: form });
      setCsrfToken(me.csrf_token);
      router.replace("/dashboard?welcome=1");
    } catch (err) {
      if (err instanceof ApiError) {
        setFields(err.fields);
        if (!Object.keys(err.fields).length) setError(err.message);
      } else {
        setError("Registration failed.");
      }
      setBusy(false);
    }
  }

  const setupMode = config?.needs_setup;
  const closed = config && !config.signup_open;
  const plan = params.get("plan");

  return (
    <AuthCard
      title={setupMode ? "Set up your Uptivora installation" : "Create your account"}
      subtitle={
        setupMode
          ? "This first account becomes the administrator of this installation."
          : plan
            ? `You’ll pick up the ${plan.charAt(0).toUpperCase() + plan.slice(1)} plan after signing up.`
            : "Start monitoring your websites in a minute."
      }
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      {!config && <div className="flex justify-center py-8"><Spinner /></div>}
      {closed && (
        <Alert tone="info" title="Registration is closed">
          Ask the administrator of this installation to create an account for you.
        </Alert>
      )}
      {config && !closed && (
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error && <Alert tone="error">{error}</Alert>}
          <TextField
            label="Full name"
            autoComplete="name"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            error={fields.full_name}
          />
          <TextField
            label="Work email"
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            error={fields.email}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            error={fields.password}
            hint="At least 10 characters. A short sentence works well."
          />
          <Button type="submit" className="w-full" loading={busy}>
            {setupMode ? "Create administrator account" : "Create account"}
          </Button>
          <p className="text-center text-xs text-fg-subtle">
            We only use your email for your account and alerts. No tracking, no newsletters.
          </p>
        </form>
      )}
    </AuthCard>
  );
}
