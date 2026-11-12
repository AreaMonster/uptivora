import type { Metadata } from "next";
import { AdminBillingView } from "./view";

export const metadata: Metadata = { title: "Billing & licences" };

export default function Page() {
  return <AdminBillingView />;
}
