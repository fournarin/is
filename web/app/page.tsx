import Link from "next/link";

import { signOut } from "@/app/actions";
import { screensFor } from "@/lib/screens";
import { ROLE_NAMES, requireAccount } from "@/lib/session";

/**
 * The shell: who you are, and which screens your role is offered.
 *
 * It offers screens, never work. A list of jobs to choose from is the one thing
 * this application may not grow (ADR-058), because choosing the easy job first
 * is exactly what the load gate exists to prevent (ADR-011).
 */
export default async function HomePage() {
  const account = await requireAccount();
  const screens = screensFor(account.role);

  return (
    <>
      <div className="who">
        <span>
          <strong>{account.display_name}</strong>
          <span className="muted"> · {ROLE_NAMES[account.role]}</span>
        </span>
        <form action={signOut}>
          <button type="submit" className="quiet">
            ออกจากระบบ
          </button>
        </form>
      </div>

      <h1>หน้าจอของคุณ</h1>

      {screens.length === 0 ? (
        <p className="card">
          บทบาทนี้ยังไม่มีหน้าจอในระบบ งานของ{ROLE_NAMES[account.role]}คือการอัปโหลดและเปลี่ยนคู่มือ
          (ADR-024) ซึ่งตอนนี้ทำผ่าน API เท่านั้น — พูดตรง ๆ ดีกว่าแสดงหน้าจอที่กดแล้วไม่มีอะไร
        </p>
      ) : (
        screens.map((screen) => (
          <section className="card" key={screen.slice}>
            <div className="screen-head">
              <h2>
                {screen.href === null ? (
                  screen.title
                ) : (
                  <Link href={screen.href}>{screen.title}</Link>
                )}
              </h2>
              {screen.href === null && <span className="pending">slice {screen.slice}</span>}
            </div>
            <p className="muted">{screen.purpose}</p>
            {screen.href === null && <p className="muted">ยังไม่ได้สร้าง</p>}
          </section>
        ))
      )}
    </>
  );
}
