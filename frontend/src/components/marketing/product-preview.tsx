import { cn } from "@/lib/format";

// Illustrative, static preview of the dashboard (not live data).
const ROWS = [
  { name: "Online shop", host: "shop.example.ch", status: "up", uptime: "100%", ms: "182 ms", seed: 3 },
  { name: "Marketing site", host: "www.example.ch", status: "up", uptime: "99.98%", ms: "96 ms", seed: 7 },
  { name: "Customer API", host: "api.example.ch", status: "down", uptime: "98.71%", ms: "—", seed: 11 },
  { name: "Status page", host: "status.example.ch", status: "up", uptime: "100%", ms: "74 ms", seed: 5 },
] as const;

function bars(seed: number, down: boolean) {
  return Array.from({ length: 45 }, (_, i) => {
    if (down && i === 44) return "down";
    if (down && (i === 43 || i === 20)) return "warn";
    if ((i * seed) % 41 === 7 && seed !== 3) return "warn";
    return "up";
  });
}

export function ProductPreview() {
  return (
    <div className="card overflow-hidden p-0 ring-1 ring-white/5" aria-label="Dashboard preview">
      <div className="flex items-center gap-2 border-b border-line bg-ink-850 px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-ink-700" />
        <span className="h-2.5 w-2.5 rounded-full bg-ink-700" />
        <span className="h-2.5 w-2.5 rounded-full bg-ink-700" />
        <span className="ml-3 hidden rounded-md bg-ink-900 px-3 py-1 text-xs text-fg-subtle sm:block">
          app.uptivora.com/dashboard
        </span>
      </div>
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
        {[
          ["Monitors", "4"],
          ["Up", "3"],
          ["Down", "1"],
          ["Uptime (24h)", "99.67%"],
        ].map(([k, v], i) => (
          <div key={k} className="bg-ink-800 px-5 py-4">
            <p className="text-xs text-fg-subtle">{k}</p>
            <p className={cn("tnum mt-1 text-xl font-semibold", i === 2 && "text-down", i === 1 && "text-up")}>
              {v}
            </p>
          </div>
        ))}
      </div>
      <ul className="divide-y divide-line">
        {ROWS.map((r) => (
          <li key={r.name} className="grid items-center gap-3 px-5 py-4 sm:grid-cols-[1.3fr_2fr_auto]">
            <div className="flex min-w-0 items-center gap-3">
              <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", r.status === "up" ? "bg-up" : "bg-down")} />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{r.name}</p>
                <p className="truncate text-xs text-fg-subtle">{r.host}</p>
              </div>
            </div>
            <div className="hidden h-7 items-end gap-[3px] sm:flex" aria-hidden>
              {bars(r.seed, r.status === "down").map((b, i) => (
                <span
                  key={i}
                  className={cn(
                    "h-full flex-1 rounded-[2px]",
                    b === "up" && "bg-up/80",
                    b === "warn" && "bg-warn/80",
                    b === "down" && "bg-down",
                  )}
                />
              ))}
            </div>
            <div className="tnum flex gap-5 text-right text-sm sm:block">
              <p className="font-medium">{r.uptime}</p>
              <p className="text-xs text-fg-subtle">{r.ms}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
