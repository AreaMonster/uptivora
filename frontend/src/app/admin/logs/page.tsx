import type { Metadata } from "next";
import { LogsView } from "./view";

export const metadata: Metadata = { title: "Logs" };

export default function Page() {
  return <LogsView />;
}
