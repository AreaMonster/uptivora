import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { MonitorDetail } from "./monitor-detail";

export const metadata: Metadata = { title: "Monitor" };

export default function MonitorPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[480px]" />}>
      <MonitorDetail />
    </Suspense>
  );
}
