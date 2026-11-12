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
          <defs>
            <linearGradient id="rt-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#233047" strokeDasharray="3 4" vertical={false} />
          <XAxis
            dataKey="t"
            tickFormatter={(v) => tickLabel(v, range)}
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            minTickGap={32}
          />
          <YAxis
            stroke="#64748b"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={(v) => `${v} ms`}
          />
          <Tooltip
            cursor={{ stroke: "#2f3d57" }}
            contentStyle={{
              background: "#131c2c",
              border: "1px solid #2f3d57",
              borderRadius: 10,
              fontSize: 12,
              color: "#e7edf6",
            }}
            labelFormatter={(v) => new Date(String(v)).toLocaleString("en-GB")}
            formatter={(v) => [formatMs(Number(v)), "Avg response"]}
          />
          <Area
            type="monotone"
            dataKey="avg_ms"
            stroke="#2dd4bf"
            strokeWidth={2}
            fill="url(#rt-fill)"
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
    <div className={cn("flex h-9 items-end gap-[2px]", className)} role="img"
      aria-label="Uptime per time bucket">
      {bars.map((p) => {
        const u = p.uptime;
        const color =
          u == null ? "bg-ink-700" : u >= 99.999 ? "bg-up/85" : u >= 50 ? "bg-warn/85" : "bg-down";
        return (
          <span
            key={p.t}
            title={`${new Date(p.t).toLocaleString("en-GB")} — ${formatUptime(u)} (${p.checks} checks)`}
            className={cn("h-full min-w-[3px] flex-1 rounded-[2px] transition-opacity hover:opacity-70", color)}
          />
        );
      })}
    </div>
  );
}
