import type { MonitorStatus } from "@/lib/api";

export type AdminOverview = {
  edition: "hosted" | "selfhosted";
  environment: string;
  billing_test_mode: boolean;
  users: { total: number; new_7d: number; active_30d: number; suspended: number; admins: number };
  monitors: { total: number; active: number; paused: number; down: number; admin_paused: number };
  checks: { last_hour: number; failed_last_hour: number; last_24h: number; per_minute: number };
  incidents: { open: number; last_24h: number };
  emails: { queued: number; failed_7d: number; sent_24h: number };
  checks_by_hour: { t: string; total: number; failed: number }[];
  subscriptions?: {
    active: number;
    past_due: number;
    cancelled: number;
    expired: number;
    mrr: { real_cents: number; test_cents: number; currency: string };
  };
  licence?: {
    installed: boolean;
    edition: string | null;
    licensee: string | null;
    license_id: string | null;
    limits: { max_monitors: number; max_users: number; min_interval_seconds: number } | null;
    error: string | null;
    source: string | null;
  };
};

export type AdminHealth = {
  status: "ok" | "degraded";
  issues: string[];
  app: {
    version: string;
    edition: string;
    environment: string;
    python: string;
    platform: string;
    hostname: string;
    api_uptime_seconds: number;
    now: string;
  };
  server: {
    disk: { total_bytes: number; used_bytes: number; free_bytes: number } | null;
    load_average: number[] | null;
    cpu_count: number | null;
  };
  database: {
    ok: boolean;
    latency_ms: number;
    version: string;
    size_bytes: number;
    connections: number;
    max_connections: number;
    largest_tables: { name: string; rows: number; bytes: number }[];
  };
  workers: {
    worker_id: string;
    hostname: string;
    pid: number;
    version: string;
    started_at: string;
    last_seen_at: string;
    checks_total: number;
    checks_failed: number;
    in_flight: number;
    alive: boolean;
  }[];
  scheduler: { overdue_monitors: number; max_delay_seconds: number };
  email: { queued: number; oldest_seconds: number; smtp_configured: boolean; smtp_host: string | null };
};

export type AdminUserRow = {
  id: string;
  email: string;
  full_name: string;
  role: "user" | "admin";
  is_active: boolean;
  email_verified: boolean;
  pending_invite: boolean;
  created_at: string;
  last_login_at: string | null;
  plan: string | null;
  subscription_status: string | null;
  monitors: number;
};

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number };

export type AdminUserDetail = {
  user: AdminUserRow;
  timezone: string;
  limits: import("@/lib/api").Limits;
  usage: { active_monitors: number; open_incidents: number };
  subscription: {
    plan: string;
    plan_code: string;
    status: string;
    is_test: boolean;
    current_period_end: string;
    cancel_at_period_end: boolean;
    provider: string;
  } | null;
  monitors: {
    id: string;
    name: string;
    url: string;
    status: MonitorStatus;
    is_paused: boolean;
    paused_reason: string | null;
    interval_seconds: number;
    last_checked_at: string | null;
  }[];
  audit: { action: string; created_at: string; ip: string | null; by_self: boolean }[];
};

export type AdminMonitorRow = {
  id: string;
  name: string;
  url: string;
  owner_email: string;
  owner_id: string;
  status: MonitorStatus;
  is_paused: boolean;
  paused_reason: "user" | "plan_limit" | "admin" | null;
  interval_seconds: number;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string;
};

export type AdminPlan = {
  id: string;
  code: string;
  name: string;
  description: string;
  price_cents: number;
  currency: string;
  interval: string;
  max_monitors: number;
  min_interval_seconds: number;
  is_active: boolean;
  is_public: boolean;
  sort_order: number;
  subscribers: number;
};

export type AdminLicenceProduct = {
  id: string;
  code: string;
  name: string;
  description: string;
  edition: string;
  price_cents: number;
  currency: string;
  limits: { max_monitors: number; max_users: number; min_interval_seconds: number };
  is_active: boolean;
  sort_order: number;
};

export type SystemEventRow = {
  id: number;
  level: string;
  source: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type AuditRow = {
  id: number;
  action: string;
  actor: string | null;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  details: Record<string, unknown>;
  created_at: string;
};
