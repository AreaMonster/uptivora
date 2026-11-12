import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { UserDetailView } from "./view";

export const metadata: Metadata = { title: "User" };

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <UserDetailView />
    </Suspense>
  );
}
