import type { Metadata } from "next";
import { DevToolsView } from "./view";

export const metadata: Metadata = { title: "Dev tools" };

export default function Page() {
  return <DevToolsView />;
}
