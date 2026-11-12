"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Alert, Button, SelectField, TextField, Toggle } from "@/components/ui";
import { ApiError, api, type FieldErrors, type Monitor } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatInterval } from "@/lib/format";

const INTERVALS = [30, 60, 120, 300, 600, 900, 1800, 3600];

type Values = {
  name: string;
  url: string;
  interval_seconds: number;
  method: "GET" | "HEAD";
  timeout_seconds: number;
  expected_status: string;
  keyword: string;
  follow_redirects: boolean;
  verify_tls: boolean;
  down_threshold: number;
  recovery_threshold: number;
  ssl_check_enabled: boolean;
  ssl_warning_days: number;
  notifications_enabled: boolean;
};

function initialValues(m: Monitor | undefined, minInterval: number): Values {
  return {
    name: m?.name ?? "",
    url: m?.url ?? "",
    interval_seconds: m?.interval_seconds ?? Math.max(300, minInterval),
    method: m?.method ?? "GET",
    timeout_seconds: m?.timeout_seconds ?? 10,
    expected_status: m?.expected_status ?? "200-399",
    keyword: m?.keyword ?? "",
    follow_redirects: m?.follow_redirects ?? true,
    verify_tls: m?.verify_tls ?? true,
    down_threshold: m?.down_threshold ?? 2,
    recovery_threshold: m?.recovery_threshold ?? 1,
    ssl_check_enabled: m?.ssl_check_enabled ?? true,
    ssl_warning_days: m?.ssl_warning_days ?? 14,
    notifications_enabled: m?.notifications_enabled ?? true,
  };
}

export function MonitorForm({ monitor }: { monitor?: Monitor }) {
  const router = useRouter();
  const { me, refresh } = useAuth();
  const minInterval = me?.limits.min_interval_seconds ?? 300;
  const [v, setV] = useState<Values>(() => initialValues(monitor, minInterval));
  const [advanced, setAdvanced] = useState(false);
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof Values>(key: K, value: Values[K]) => setV((s) => ({ ...s, [key]: value }));

  const intervalOptions = INTERVALS.filter((i) => i >= minInterval);
  if (monitor && !intervalOptions.includes(monitor.interval_seconds)) {
    intervalOptions.push(monitor.interval_seconds);
    intervalOptions.sort((a, b) => a - b);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    const body = { ...v, keyword: v.keyword.trim() || (monitor ? "" : null) };
    try {
      const saved = monitor
        ? await api<Monitor>(`/api/monitors/${monitor.id}`, { method: "PATCH", body })
        : await api<Monitor>("/api/monitors", { method: "POST", body });
      void refresh();
      router.push(`/monitors/${saved.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setFields(err.fields);
        const advancedKeys = ["method", "timeout_seconds", "expected_status", "keyword",
          "down_threshold", "recovery_threshold", "ssl_warning_days"];
        if (Object.keys(err.fields).some((k) => advancedKeys.includes(k))) setAdvanced(true);
        if (!Object.keys(err.fields).length || err.fields._) setError(err.fields._ ?? err.message);
      } else {
        setError("Saving failed.");
      }
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card space-y-6 p-6 sm:p-8" noValidate>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField label="Name" required maxLength={120} placeholder="Online shop" value={v.name}
          onChange={(e) => set("name", e.target.value)} error={fields.name} />
        <SelectField label="Check every" value={v.interval_seconds}
          onChange={(e) => set("interval_seconds", Number(e.target.value))}
          error={fields.interval_seconds}
          hint={minInterval > 30 ? `Fastest interval on your plan: ${formatInterval(minInterval)}.` : undefined}>
          {intervalOptions.map((i) => (
            <option key={i} value={i}>{formatInterval(i)}</option>
          ))}
        </SelectField>
        <TextField className="sm:col-span-2" label="URL" required type="url" inputMode="url"
          placeholder="https://www.example.ch" value={v.url}
          onChange={(e) => set("url", e.target.value)} error={fields.url}
          hint="Public http(s) address. Private networks and localhost are not allowed." />
      </div>

      <div className="divide-y divide-line rounded-xl border border-line bg-ink-850 px-4">
        <Toggle label="Email alerts for this monitor" checked={v.notifications_enabled}
          onChange={(x) => set("notifications_enabled", x)}
          description="Outage and recovery emails, according to your notification settings." />
        <Toggle label="Watch the SSL certificate" checked={v.ssl_check_enabled}
          onChange={(x) => set("ssl_check_enabled", x)}
          description="Warn before the certificate of an https:// site expires." />
      </div>

      <div>
        <button type="button" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-fg-muted hover:text-fg">
          <ChevronDown className={cn("h-4 w-4 transition-transform", advanced && "rotate-180")} />
          Advanced settings
        </button>
        {advanced && (
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <SelectField label="HTTP method" value={v.method} error={fields.method}
              onChange={(e) => set("method", e.target.value as Values["method"])}>
              <option value="GET">GET</option>
              <option value="HEAD">HEAD</option>
            </SelectField>
            <TextField label="Timeout (seconds)" type="number" min={1} max={60}
              value={v.timeout_seconds} error={fields.timeout_seconds}
              onChange={(e) => set("timeout_seconds", Number(e.target.value))} />
            <TextField label="Expected status codes" value={v.expected_status}
              error={fields.expected_status} hint="e.g. 200-299,301"
              onChange={(e) => set("expected_status", e.target.value)} />
            <TextField label="Required keyword (optional)" value={v.keyword} maxLength={200}
              error={fields.keyword} hint="Fails the check if this text is missing (GET only)."
              onChange={(e) => set("keyword", e.target.value)} />
            <TextField label="Confirm outage after" type="number" min={1} max={10}
              value={v.down_threshold} error={fields.down_threshold} hint="consecutive failed checks"
              onChange={(e) => set("down_threshold", Number(e.target.value))} />
            <TextField label="Recover after" type="number" min={1} max={10}
              value={v.recovery_threshold} error={fields.recovery_threshold}
              hint="consecutive successful checks"
              onChange={(e) => set("recovery_threshold", Number(e.target.value))} />
            <TextField label="SSL warning (days before expiry)" type="number" min={1} max={90}
              value={v.ssl_warning_days} error={fields.ssl_warning_days}
              onChange={(e) => set("ssl_warning_days", Number(e.target.value))} />
            <div className="divide-y divide-line rounded-xl border border-line bg-ink-850 px-4 sm:col-span-2">
              <Toggle label="Follow redirects" checked={v.follow_redirects}
                onChange={(x) => set("follow_redirects", x)}
                description="Up to 5 hops; each target is security-checked." />
              <Toggle label="Verify TLS certificate" checked={v.verify_tls}
                onChange={(x) => set("verify_tls", x)}
                description="Treat invalid or expired certificates as a failure." />
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col-reverse gap-2 border-t border-line pt-6 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={() => router.back()}>Cancel</Button>
        <Button type="submit" loading={busy}>{monitor ? "Save changes" : "Create monitor"}</Button>
      </div>
    </form>
  );
}
