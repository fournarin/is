import { redirect } from "next/navigation";

import { SignInForm } from "@/app/sign-in/sign-in-form";
import { currentAccount } from "@/lib/session";

/**
 * The only screen a visitor without a session reaches.
 *
 * ADR-024 refuses a mode with authentication turned off, "not even for a demo",
 * so there is no way past this page and no guest view behind it.
 */
export default async function SignInPage() {
  if ((await currentAccount()) !== null) {
    redirect("/");
  }

  return (
    <>
      <h1>ระบบแจ้งซ่อมล่วงหน้า</h1>
      <p className="muted">เข้าสู่ระบบด้วยบัญชีที่วิศวกรตั้งไว้ให้</p>
      <SignInForm />
    </>
  );
}
