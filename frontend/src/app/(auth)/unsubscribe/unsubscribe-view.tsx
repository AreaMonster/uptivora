"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Alert, Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

export function Unsubscribe() {
  const params = useSearchParams();
  const k = params.get("k");
  const id = params.get("id");
  const t = params.get("t");
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = (k === "a" || k === "c") && id && t;

  // Requires a click: link scanners in mail systems must not unsubscribe people by visiting.
  async function confirm() {
    setBusy(true);
    try {
      const res = await api<{ email: string }>("/api/notifications/unsubscribe", {
        method: "POST", body: { k, id, t },
      });
      setState({ ok: true, text: `${res.email} will no longer receive Uptivora alert emails.` });
    } catch (err) {
      setState({ ok: false, text: err instanceof ApiError ? err.message : "Unsubscribing failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Unsubscribe from alerts">
      {!valid ? (
        <Alert tone="error">This unsubscribe link is incomplete. Open it again from the email.</Alert>
      ) : state ? (
        <Alert tone={state.ok ? "success" : "error"} title={state.ok ? "Unsubscribed" : undefined}>
          {state.text}
          {state.ok && k === "a" && " You can turn alerts back on in your notification settings."}
        </Alert>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-fg-muted">
            {k === "a"
              ? "Stop sending monitoring alerts to your account email? Account and security emails are not affected."
              : "Stop receiving monitoring alerts at this address? The person who added you will see that you unsubscribed."}
          </p>
          <Button className="w-full" onClick={confirm} loading={busy}>Unsubscribe</Button>
        </div>
      )}
    </AuthCard>
  );
}
