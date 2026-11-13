import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/legal-page";
import { TermsText } from "@/content/legal/pages";

export const metadata: Metadata = { title: "Terms of service", description: "The rules for using the hosted Uptivora service." };

export default function Page() {
  return (
    <LegalPage title="Terms of service">
      <TermsText />
    </LegalPage>
  );
}
