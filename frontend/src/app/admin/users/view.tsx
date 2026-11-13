"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Alert, Badge, Button, PageHeader, Skeleton } from "@/components/ui";
import { Invitations } from "@/components/admin/invitations";
import type { AdminUserRow, Paged } from "@/lib/admin-types";
import { cn, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "suspended", label: "Suspended" },
] as const;

export function UsersView() {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const id = setTimeout(() => {
      setQ(input.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [input]);

  const params = new URLSearchParams({ status, page: String(page), page_size: "25" });
  if (q) params.set("q", q);
  const { data, error, reload } = useApi<Paged<AdminUserRow>>(`/api/admin/users?${params}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Users" description={data ? `${data.total} matching accounts` : undefined} />
      <Invitations onChanged={() => void reload()} />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1">
          <span className="sr-only">Search users</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" />
          <input className="input pl-9" placeholder="Search by email or name" value={input}
            onChange={(e) => setInput(e.target.value)} />
        </label>
        <div className="inline-flex rounded-[3px] border border-line bg-sunken p-0.5" role="tablist">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={status === f.key}
              onClick={() => { setStatus(f.key); setPage(1); }}
              className={cn("rounded-[3px] px-3 py-1.5 text-sm font-medium",
                status === f.key ? "bg-muted text-fg" : "text-fg-muted hover:text-fg")}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && <Alert tone="error">{error.message}</Alert>}
      {!data && !error && <Skeleton className="h-96" />}
      {data && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead className="border-b border-line text-left text-xs text-fg-subtle">
                <tr>
                  <th className="px-5 py-3 font-medium">User</th>
                  <th className="px-2 py-3 font-medium">Plan</th>
                  <th className="px-2 py-3 text-right font-medium">Monitors</th>
                  <th className="px-2 py-3 font-medium">Status</th>
                  <th className="hidden px-2 py-3 font-medium lg:table-cell">Joined</th>
                  <th className="px-5 py-3 font-medium">Last login</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((u) => (
                  <tr key={u.id} className="hover:bg-hover/60">
                    <td className="px-5 py-3">
                      <Link href={`/admin/users/${u.id}`} className="font-medium hover:text-accent">{u.email}</Link>
                      <p className="text-xs text-fg-subtle">{u.full_name || "—"}</p>
                    </td>
                    <td className="px-2 py-3">{u.plan ?? <span className="text-fg-subtle">none</span>}</td>
                    <td className="tnum px-2 py-3 text-right">{u.monitors}</td>
                    <td className="px-2 py-3">
                      <span className="flex flex-wrap gap-1">
                        {u.is_active ? <Badge tone="up">Active</Badge> : <Badge tone="down">Suspended</Badge>}
                        {u.role === "admin" && <Badge tone="warn">Admin</Badge>}
                        {u.pending_invite ? <Badge tone="warn">Invited</Badge> : !u.email_verified && <Badge>Unconfirmed</Badge>}
                      </span>
                    </td>
                    <td className="hidden whitespace-nowrap px-2 py-3 text-fg-muted lg:table-cell">{timeAgo(u.created_at)}</td>
                    <td className="whitespace-nowrap px-5 py-3 text-fg-muted">{u.last_login_at ? timeAgo(u.last_login_at) : "never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.items.length === 0 && <p className="px-5 py-8 text-center text-sm text-fg-subtle">No users match.</p>}
          {pages > 1 && (
            <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
              <span className="text-fg-muted">Page {page} of {pages}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
