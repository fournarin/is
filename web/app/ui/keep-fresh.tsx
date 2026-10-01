"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Re-reads the page every `seconds` while nobody is typing into it.
 *
 * The board is a whiteboard that changes on its own: a round proposes every
 * five minutes and technicians close jobs. In the owner's second trial a card
 * said "if you do not answer by 22:37 it goes back to the queue" at 22:50,
 * because the page had not been read again since it was opened (ADR-120).
 * A refresh never runs while a reason is being typed or a form is open, so it
 * cannot throw away what somebody was writing.
 */
export function KeepFresh({ seconds = 30 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => {
      const busy =
        document.activeElement instanceof HTMLTextAreaElement ||
        document.activeElement instanceof HTMLInputElement ||
        document.querySelector("details[open]") !== null;
      if (!busy && document.visibilityState === "visible") {
        router.refresh();
      }
    }, seconds * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
