"use client";

import { WifiOff } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

/**
 * Says so when the phone has lost the network (ADR-134).
 *
 * A cell's Wi-Fi drops while somebody is mid-job, and the next tap then fails
 * with the browser's own error page. The strip comes first: what is on the
 * screen can still be read, and what was done is already recorded, so nobody
 * starts the step again. Drawn only while offline; nothing at all otherwise.
 */
export function OfflineStrip({ children, synthetic }: { children: ReactNode; synthetic: boolean }) {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  // In the synthetic banner's row, not a row of its own, so the step's button
  // stays where the thumb expects it (set 1 review); the banner's words stay in it.
  if (!offline) return <>{children}</>;
  return (
    <div className="offline" role="status">
      <WifiOff size={24} aria-hidden />
      <span>
        <b>Wi-Fi หลุด</b> · ที่ทำไว้ไม่หาย{synthetic && " · จำลอง"}
      </span>
    </div>
  );
}
