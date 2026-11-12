import type { Metadata } from "next";
import { ConfirmAlerts } from "./confirm-view";

export const metadata: Metadata = { title: "Confirm alerts", robots: { index: false } };

export default function Page() {
  return <ConfirmAlerts />;
}
