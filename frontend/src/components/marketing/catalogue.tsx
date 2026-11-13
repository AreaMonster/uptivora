import Link from "next/link";
import { Skeleton } from "@/components/ui";
import type { LicenceProduct, Plan, PublicConfig } from "@/lib/api";
import { formatInterval, formatMoney } from "@/lib/format";
import { serverFetch } from "@/lib/server-api";

type Catalogue = { plans: Plan[]; licences: LicenceProduct[] };

/** Prices come from the admin-editable catalogue at request time. */
export async function loadCatalogue() {
  const [catalogue, config] = await Promise.all([
    serverFetch<Catalogue>("/api/public/plans"),
    serverFetch<PublicConfig>("/api/public/config"),
  ]);
  return { catalogue, testMode: !!config?.billing_test_mode };
}

export function TestModeNote() {
  return (
    <p className="border-l-[3px] border-warn bg-warn-soft px-4 py-2.5 text-sm">
      <strong className="font-semibold">Test mode.</strong>{" "}
      <span className="text-fg-muted">
        Payments are simulated while billing is being set up. No money is charged.
      </span>
    </p>
  );
}

export async function PlanTable({ chooseLinks = false }: { chooseLinks?: boolean }) {
  const { catalogue, testMode } = await loadCatalogue();
  if (!catalogue?.plans.length) {
    return <p className="text-sm text-fg-muted">Prices are unavailable right now. Please try again shortly.</p>;
  }
  return (
    <div className="space-y-4">
      {testMode && <TestModeNote />}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-t border-fg text-left text-[15px]">
          <thead>
            <tr className="border-b border-line text-xs text-fg-subtle">
              <th className="py-2.5 pr-4 font-normal">Plan</th>
              <th className="py-2.5 pr-4 text-right font-normal">Websites</th>
              <th className="py-2.5 pr-4 text-right font-normal">Checked every</th>
              <th className="py-2.5 pr-4 text-right font-normal">Per month</th>
              {chooseLinks && <th className="py-2.5" />}
            </tr>
          </thead>
          <tbody>
            {catalogue.plans.map((p) => (
              <tr key={p.code} className="border-b border-line">
                <td className="py-4 pr-4">
                  <span className="font-semibold">{p.name}</span>
                  {p.description && <span className="block text-sm text-fg-muted">{p.description}</span>}
                </td>
                <td className="tnum py-4 pr-4 text-right font-mono">{p.max_monitors}</td>
                <td className="tnum py-4 pr-4 text-right font-mono">{formatInterval(p.min_interval_seconds)}</td>
                <td className="tnum py-4 pr-4 text-right font-mono font-medium">
                  {formatMoney(p.price_cents, p.currency)}
                </td>
                {chooseLinks && (
                  <td className="py-4 text-right">
                    <Link href={`/register?plan=${p.code}`} className="link whitespace-nowrap text-sm">
                      Choose {p.name}
                    </Link>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export async function LicenceTable() {
  const { catalogue } = await loadCatalogue();
  if (!catalogue?.licences.length) {
    return <p className="text-sm text-fg-muted">Licence prices are unavailable right now.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-t border-fg text-left text-[15px]">
        <thead>
          <tr className="border-b border-line text-xs text-fg-subtle">
            <th className="py-2.5 pr-4 font-normal">Licence</th>
            <th className="py-2.5 pr-4 text-right font-normal">Websites</th>
            <th className="py-2.5 pr-4 text-right font-normal">Users</th>
            <th className="py-2.5 pr-4 text-right font-normal">Checked every</th>
            <th className="py-2.5 text-right font-normal">Once</th>
          </tr>
        </thead>
        <tbody>
          {catalogue.licences.map((l) => (
            <tr key={l.code} className="border-b border-line">
              <td className="py-4 pr-4 font-semibold">{l.name}</td>
              <td className="tnum py-4 pr-4 text-right font-mono">{l.limits.max_monitors || "no limit"}</td>
              <td className="tnum py-4 pr-4 text-right font-mono">{l.limits.max_users || "no limit"}</td>
              <td className="tnum py-4 pr-4 text-right font-mono">{formatInterval(l.limits.min_interval_seconds)}</td>
              <td className="tnum py-4 text-right font-mono font-medium">{formatMoney(l.price_cents, l.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="space-y-2 border-t border-fg pt-3">
      {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}
    </div>
  );
}
