"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SeriesPoint } from "@/lib/api";
import { cn, formatMs, formatUptime } from "@/lib/format";

export const TOOLTIP_STYLE = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-line-strong)",
  borderRadius: 3,
  fontSize: 12,
  fontFamily: "var(--font-mono)",
  color: "var(--color-fg)",
  boxShadow: "none",
};

function tickLabel(iso: string, range: string): string {
  const d = new Date(iso);
  if (range === "24h") return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function ResponseTimeChart({ points, range }: { points: SeriesPoint[]; range: string }) {
  const data = points.filter((p) => p.avg_ms != null);
  if (!data.length) {
    return (
      <div className="grid h-64 place-items-center text-sm text-fg-subtle">
        No response-time data for this period yet.
      </div>
    );
  }
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={(v) => tickLabel(v, range)}
            stroke="var(--color-fg-subtle)"
            fontSize={11}
            fontFamily="var(--font-mono)"
            tickLine={false}
            axisLine={{ stroke: "var(--color-line-strong)" }}
            minTickGap={32}
          />
          <YAxis
            stroke="var(--color-fg-subtle)"
            fontSize={11}
            fontFamily="var(--font-mono)"
            tickLine={false}
            axisLine={false}
            width={60}
            tickFormatter={(v) => `${v} ms`}
          />
          <Tooltip
            cursor={{ stroke: "var(--color-line-strong)" }}
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(v) => new Date(String(v)).toLocaleString("en-GB")}
            formatter={(v) => [formatMs(Number(v)), "Avg response"]}
          />
          <Area
            type="linear"
            dataKey="avg_ms"
            stroke="var(--color-fg)"
            strokeWidth={1.5}
            fill="var(--color-fg)"
            fillOpacity={0.06}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** One bar per bucket: green = 100 %, amber = partial, red = mostly down, grey = no data. */
export function UptimeBars({ points, className }: { points: SeriesPoint[]; className?: string }) {
  const bars = points.slice(-90);
  if (!bars.length) {
    return <p className="text-sm text-fg-subtle">No checks recorded in this period yet.</p>;
  }
  return (
    <div className={cn("flex h-8 items-end gap-px", className)} role="img"
      aria-label="Uptime per time bucket">
      {bars.map((p) => {
        const u = p.uptime;
        const color =
          u == null ? "bg-muted" : u >= 99.999 ? "bg-up" : u >= 50 ? "bg-warn" : "bg-down";
        return (
          <span
            key={p.t}
            title={`${new Date(p.t).toLocaleString("en-GB")} — ${formatUptime(u)} (${p.checks} checks)`}
            className={cn("h-full min-w-[2px] flex-1 transition-opacity hover:opacity-60", color)}
          />
        );
      })}
    </div>
  );
}
