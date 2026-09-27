import Link from "next/link";
import type { ReactNode } from "react";

import { signOut } from "@/app/actions";
import { tabsFor } from "@/lib/screens";
import { ROLE_NAMES, type Account } from "@/lib/session";

/**
 * The frame every signed-in screen sits in: who you are at the top, your tabs
 * at the bottom, as on the phone apps the floor already uses (ADR-093).
 */
export function Shell({
  account,
  current,
  children,
}: {
  account: Account;
  current: string;
  children: ReactNode;
}) {
  const tabs = tabsFor(account.role);
  return (
    <>
      <header className="appbar">
        <div className="appbar-inner">
          <span className="brand">🛠️ แจ้งซ่อมล่วงหน้า</span>
          <span className="person">
            {account.display_name}
            <br />
            <small>{ROLE_NAMES[account.role]}</small>
          </span>
          <form action={signOut}>
            <button type="submit">ออก</button>
          </form>
        </div>
      </header>
      <main>{children}</main>
      {tabs.length > 1 && (
        <nav className="tabbar" aria-label="เมนูหลัก">
          <div className="tabbar-inner">
            {tabs.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className={tab.href === current ? "current" : undefined}
                aria-current={tab.href === current ? "page" : undefined}
              >
                <span className="icon" aria-hidden="true">
                  {tab.icon}
                </span>
                {tab.label}
              </Link>
            ))}
          </div>
        </nav>
      )}
    </>
  );
}

/** A screen this role is not offered: say so plainly, and point home. */
export function NotYours({ home, what }: { home: string; what: string }) {
  return (
    <div className="card empty">
      <span className="icon" aria-hidden="true">
        🔒
      </span>
      <p>{what}</p>
      <Link className="button-link quiet" href={home}>
        กลับหน้าหลักของฉัน
      </Link>
    </div>
  );
}
