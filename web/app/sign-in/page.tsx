import { WifiOff, Wrench } from "lucide-react";
import { redirect } from "next/navigation";

import { SignInForm } from "@/app/sign-in/sign-in-form";
import { Th } from "@/app/ui/v2/frame";
import "@/app/ui/v2/v2.css";
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
    <div className="v2 si">
      <main className="si-col">
        <div className="si-plate">
          <span className="si-mark" aria-hidden>
            <Wrench size={32} />
          </span>
          <div>
            <h1>แจ้งซ่อมล่วงหน้า</h1>
            <p>
              <Th>ระบบงานซ่อมบำรุงของสายการผลิต</Th>
            </p>
          </div>
        </div>
        <p className="si-lead">
          <Th>ใช้ชื่อผู้ใช้และรหัสผ่านที่หัวหน้าหรือวิศวกรให้ไว้</Th>
        </p>
        {unreachable && (
          <div className="callout is-bad" role="alert">
            <WifiOff size={24} aria-hidden />
            <div>{UNREACHABLE} ระบบอาจกำลังเริ่มใหม่ รอสักครู่แล้วลองอีกครั้ง</div>
          </div>
        )}
        <SignInForm />
      </main>
    </div>
  );
}
