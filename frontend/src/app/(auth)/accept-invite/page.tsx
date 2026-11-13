import type { Metadata } from "next";
import { AcceptInvite } from "./accept-view";

export const metadata: Metadata = { title: "Accept invitation", robots: { index: false } };

export default function Page() {
  return <AcceptInvite />;
}
