"use client";

import { WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * Says so when the phone has lost the network (ADR-134).
 *
 * A cell's Wi-Fi drops while somebody is mid-job, and the next tap then fails
 * with the browser's own error page. The strip comes first: what is on the
 * screen can still be read, and what was done is already recorded, so nobody
 * starts the step again. Drawn only while offline; nothing at all otherwise.
 */
export function OfflineStrip() {
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
  if (!offline) return null;
  return (
    <div className="offline" role="status">
      <WifiOff size={24} aria-hidden />
      <span>
        <b>Wi-Fi หลุด</b> · หน้านี้ยังอ่านได้ ขั้นที่ทำแล้วบันทึกไว้แล้ว กดต่อได้เมื่อสัญญาณกลับมา
      </span>
    </div>
  );
}
