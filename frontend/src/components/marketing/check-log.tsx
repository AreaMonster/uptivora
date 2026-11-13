import { cn } from "@/lib/format";

/** A worked example of one outage, shown as the check log and the two emails it produces. */
const ROWS: { t: string; code: string; ms: string; note?: string; tone?: "down" | "up" }[] = [
  { t: "14:01:10", code: "200", ms: "184 ms" },
  { t: "14:01:40", code: "200", ms: "179 ms" },
  { t: "14:02:10", code: "503", ms: "—", note: "failed, re-checking in 30 s", tone: "down" },
  { t: "14:02:40", code: "503", ms: "—", note: "confirmed → email sent", tone: "down" },
  { t: "14:03:10", code: "503", ms: "—", tone: "down" },
  { t: "…", code: "", ms: "" },
  { t: "14:09:40", code: "200", ms: "212 ms", note: "recovered → email sent", tone: "up" },
  { t: "14:10:10", code: "200", ms: "188 ms" },
];

export function CheckLog() {
  return (
    <figure className="font-mono text-[12.5px]">
      <div className="card overflow-hidden">
        <div className="flex items-baseline justify-between border-b border-line px-4 py-2.5">
          <span className="text-fg">shop.example.ch</span>
          <span className="text-fg-subtle">GET / · every 30 s</span>
        </div>
        <table className="w-full">
          <tbody>
            {ROWS.map((r, i) => (
              <tr key={i} className={cn("border-b border-line/70 last:border-0", r.tone === "down" && "bg-down-soft")}>
                <td className="w-[1%] whitespace-nowrap py-1.5 pl-4 pr-4 text-fg-subtle">{r.t}</td>
                <td className={cn("w-[1%] pr-4",
                  r.tone === "down" ? "text-down-ink" : r.code ? "text-up-ink" : "")}>{r.code}</td>
                <td className="w-[1%] whitespace-nowrap pr-4 text-right text-fg-muted">{r.ms}</td>
                <td className={cn("pr-4 text-right sm:text-left",
                  r.tone === "down" ? "text-down-ink" : "text-up-ink")}>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Mail tone="down" time="14:02:41" subject="DOWN: Shop" line="503 Service Unavailable" />
        <Mail tone="up" time="14:09:41" subject="RECOVERED: Shop (down 7 min)" line="Back up after 7 min 30 s" />
      </div>
      <figcaption className="mt-3 font-sans text-xs text-fg-subtle">
        Example: one outage, two emails. Times and site are illustrative.
      </figcaption>
    </figure>
  );
}

function Mail({ tone, time, subject, line }: { tone: "up" | "down"; time: string; subject: string; line: string }) {
  return (
    <div className={cn("card border-t-[3px] px-3.5 py-2.5", tone === "down" ? "border-t-down" : "border-t-up")}>
      <div className="flex justify-between text-[11px] text-fg-subtle">
        <span>alerts@…</span>
        <span>{time}</span>
      </div>
      <p className="mt-1 truncate font-sans text-[13px] font-semibold text-fg">{subject}</p>
      <p className="truncate font-sans text-xs text-fg-muted">{line}</p>
    </div>
  );
}
