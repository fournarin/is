"use client";

import { useEffect } from "react";

/**
 * Marks the page while the phone has lost the network (ADR-134, ADR-136).
 *
 * A cell's Wi-Fi drops while somebody is mid-job, and the next tap then fails.
 * What changes is drawn by CSS from this one mark: the clock in the top bar
 * becomes "Wi-Fi หลุด", and a step that records confirmations says they are
 * not being recorded. Nothing moves - the synthetic banner keeps its words and
 * the step's button stays where the thumb expects it (set 1 and 2 reviews).
 */
export function OfflineWatch() {
  useEffect(() => {
    const update = () => {
      if (navigator.onLine) delete document.documentElement.dataset.offline;
      else document.documentElement.dataset.offline = "1";
    };
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return null;
}
