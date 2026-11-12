import type { Metadata } from "next";
import { ResetPasswordPage } from "./reset-view";

export const metadata: Metadata = { title: "Choose a new password" };

export default function Page() {
  return <ResetPasswordPage />;
}
