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
    <main>
      <div className="card" style={{ marginTop: "12vh" }}>
        <p style={{ fontSize: "2.5rem", margin: 0 }} aria-hidden="true">
          🛠️
        </p>
        <h1>แจ้งซ่อมล่วงหน้า</h1>
        <p className="muted">เข้าสู่ระบบด้วยชื่อผู้ใช้และรหัสผ่านที่หัวหน้าหรือวิศวกรให้ไว้</p>
        <SignInForm />
      </div>
    </main>
  );
}
