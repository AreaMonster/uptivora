import type { Metadata } from "next";
import { LicenceView } from "./view";

export const metadata: Metadata = { title: "Licence" };

export default function Page() {
  return <LicenceView />;
}
