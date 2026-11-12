import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { BillingView } from "./billing-view";

export const metadata: Metadata = { title: "Billing" };

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <BillingView />
    </Suspense>
  );
}
