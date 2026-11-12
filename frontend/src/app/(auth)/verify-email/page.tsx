import type { Metadata } from "next";
import { VerifyEmailPage } from "./verify-view";

export const metadata: Metadata = { title: "Confirm email" };

export default function Page() {
  return <VerifyEmailPage />;
}
