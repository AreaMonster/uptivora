import type { Metadata } from "next";
import { Suspense } from "react";
import { Unsubscribe } from "./unsubscribe-view";

export const metadata: Metadata = { title: "Unsubscribe", robots: { index: false } };

export default function Page() {
  return (
    <Suspense>
      <Unsubscribe />
    </Suspense>
  );
}
