import { redirect } from "next/navigation";

import { SignInForm } from "@/app/sign-in/sign-in-form";
import { ApiUnreachable, UNREACHABLE } from "@/lib/api";
import { currentAccount } from "@/lib/session";

/**
 * The only screen a visitor without a session reaches.
 *
 * ADR-024 refuses a mode with authentication turned off, "not even for a demo",
 * so there is no way past this page and no guest view behind it.
 */
export default async function SignInPage() {
  // The form is shown even when the API cannot be asked who this is: it is the
  // one page that must never become an error page, and it says why signing in
  // will not work yet rather than leaving a blank screen.
  let unreachable = false;
  try {
    if ((await currentAccount()) !== null) {
      redirect("/");
    }
  } catch (error) {
    if (!(error instanceof ApiUnreachable)) {
      throw error;
    }
    unreachable = true;
  }

  return (
    <main>
      <div className="card" style={{ marginTop: "12vh" }}>
        <p style={{ fontSize: "2.5rem", margin: 0 }} aria-hidden="true">
          🛠️
        </p>
        <h1>แจ้งซ่อมล่วงหน้า</h1>
        <p className="muted">เข้าสู่ระบบด้วยชื่อผู้ใช้และรหัสผ่านที่หัวหน้าหรือวิศวกรให้ไว้</p>
        {unreachable && (
          <p className="warning" role="alert">
            {UNREACHABLE} ระบบอาจกำลังเริ่มใหม่ รอสักครู่แล้วลองอีกครั้ง
          </p>
        )}
        <SignInForm />
      </div>
    </main>
  );
}
