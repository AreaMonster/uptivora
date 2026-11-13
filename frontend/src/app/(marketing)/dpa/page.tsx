import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/legal-page";
import { DpaText } from "@/content/legal/pages";

export const metadata: Metadata = { title: "Data processing agreement", description: "How Uptivora processes personal data on behalf of business customers." };

export default function Page() {
  return (
    <LegalPage title="Data processing agreement">
      <DpaText />
    </LegalPage>
  );
}
