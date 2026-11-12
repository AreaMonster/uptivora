/**
 * Browser API client. Same-origin requests only; the session lives in an HttpOnly cookie
 * and every state-changing request carries the per-session CSRF token.
 */

export type FieldErrors = Record<string, string>;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: FieldErrors = {},
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export async function api<T = unknown>(
  path: string,
  init: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method) && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
      signal: init.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach the server. Check your connection.");
  }

  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string; fields?: FieldErrors } })
      ?.error;
    throw new ApiError(
      res.status,
      e?.code ?? "http_error",
      e?.message ?? `Request failed (${res.status})`,
      e?.fields ?? {},
    );
  }
  return data as T;
}

// --- Shared API types ------------------------------------------------------------------------

export type Limits = {
  max_monitors: number | null;
  min_interval_seconds: number;
  max_users: number | null;
  scope: "user" | "instance";
  source: "plan" | "no_plan" | "admin" | "licence" | "unlicensed";
  plan_code: string | null;
  plan_name: string | null;
  licensee: string | null;
  edition: string | null;
};

export type Me = {
  user: {
    id: string;
    email: string;
    full_name: string;
    role: "user" | "admin";
    email_verified: boolean;
    timezone: string;
    created_at: string | null;
  };
  csrf_token: string;
  limits: Limits;
  usage: { active_monitors: number };
};

export type MonitorStatus = "pending" | "up" | "down" | "paused";

export type Monitor = {
  id: string;
  name: string;
  url: string;
  method: "GET" | "HEAD";
  interval_seconds: number;
  timeout_seconds: number;
  expected_status: string;
  keyword: string | null;
  follow_redirects: boolean;
  verify_tls: boolean;
  down_threshold: number;
  recovery_threshold: number;
  notifications_enabled: boolean;
  ssl_check_enabled: boolean;
  ssl_warning_days: number;
  is_paused: boolean;
  paused_reason: "user" | "plan_limit" | "admin" | null;
  status: MonitorStatus;
  last_checked_at: string | null;
  last_status_change_at: string | null;
  last_response_ms: number | null;
  last_status_code: number | null;
  last_error: string | null;
  ssl_expires_at: string | null;
  ssl_issuer: string | null;
  ssl_error: string | null;
  created_at: string;
  uptime_24h: number | null;
};

export type Incident = {
  id: string;
  monitor_id: string;
  monitor_name?: string;
  started_at: string;
  resolved_at: string | null;
  cause: string;
  error_kind: string | null;
  status_code: number | null;
  duration_seconds: number | null;
};

export type SeriesPoint = { t: string; checks: number; uptime: number | null; avg_ms: number | null };

export type PublicConfig = {
  edition: "hosted" | "selfhosted";
  version: string;
  billing_test_mode: boolean;
  billing_enabled: boolean;
  signup_open: boolean;
  needs_setup: boolean;
  environment: string;
};

export type Plan = {
  code: string;
  name: string;
  description: string;
  price_cents: number;
  currency: string;
  interval: string;
  max_monitors: number;
  min_interval_seconds: number;
};

export type LicenceProduct = {
  code: string;
  name: string;
  description: string;
  edition: string;
  price_cents: number;
  currency: string;
  limits: { max_monitors: number; max_users: number; min_interval_seconds: number };
};

export type NotificationPrefs = {
  notify_down: boolean;
  notify_recovery: boolean;
  notify_ssl: boolean;
  ssl_warning_days: number;
  send_to_account_email: boolean;
};

export type AlertContact = {
  id: string;
  email: string;
  is_enabled: boolean;
  status: "pending" | "confirmed";
  verified_at: string | null;
  created_at: string | null;
};

export type DeliveryLogEntry = {
  id: string;
  kind: "monitor_down" | "monitor_up" | "ssl_expiring" | "ssl_error" | "test";
  recipient: string;
  subject: string;
  status: "pending" | "sending" | "sent" | "failed" | "cancelled";
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
  incident_id: string | null;
  monitor_id: string | null;
};

export type IncidentItem = Incident & {
  monitor_name: string;
  acknowledged_at: string | null;
  note: string | null;
};

export type IncidentPage = { items: IncidentItem[]; next_before: string | null };

export type IncidentSummary = {
  days: number;
  total: number;
  open: number;
  downtime_seconds: number;
  mean_time_to_recovery_seconds: number | null;
};

export type IncidentDetail = {
  incident: IncidentItem & { acknowledged_by: string | null };
  monitor: { id: string; name: string; url: string; status: MonitorStatus; interval_seconds: number };
  checks: {
    checked_at: string;
    is_up: boolean;
    status_code: number | null;
    response_ms: number | null;
    error_kind: string | null;
    error: string | null;
  }[];
  notifications: {
    kind: string;
    recipient: string;
    status: string;
    created_at: string;
    sent_at: string | null;
    last_error: string | null;
  }[];
};

export type BillingPlan = Plan & { interval: string };

export type BillingSummary = {
  enabled: boolean;
  test_mode: boolean;
  subscription: {
    plan: BillingPlan;
    status: "active" | "past_due" | "cancelled";
    is_test: boolean;
    provider: string;
    current_period_start: string;
    current_period_end: string;
    cancel_at_period_end: boolean;
    pending_plan: BillingPlan | null;
    simulate_failure: boolean;
    grace_until: string | null;
  } | null;
  usage: { active_monitors: number };
  plans: BillingPlan[];
  payments: {
    id: string;
    amount_cents: number;
    currency: string;
    status: "pending" | "succeeded" | "failed" | "refunded";
    description: string;
    is_test: boolean;
    created_at: string;
  }[];
  licence_products: LicenceProduct[];
  licence_orders: {
    id: string;
    product: string;
    status: "pending_payment" | "paid" | "fulfilled" | "refunded" | "cancelled";
    price_cents: number;
    currency: string;
    is_test: boolean;
    licensee_name: string;
    created_at: string;
    fulfilled_at: string | null;
  }[];
};

export type BillingQuote = {
  action: "subscribe" | "upgrade" | "downgrade" | "none";
  amount_cents: number;
  currency: string;
  effective_at: string;
  plan: BillingPlan;
  current_plan: BillingPlan | null;
  test_mode: boolean;
};
