"use client";

import { useEffect } from "react";

/**
 * How every sheet behaves once the page has its script (Q13 review item 6):
 * opening one moves focus into it, closing returns focus to the row that opened
 * it, Escape closes it, and while it is open the dimmed backdrop - the summary -
 * is named "ปิดแผงนี้" for a screen reader. Without the script the sheets still
 * open and close by tapping; this only adds what a keyboard and a reader need.
 */
export function SheetFocus() {
  useEffect(() => {
    const onToggle = (event: Event) => {
      const sheet = event.target;
      if (!(sheet instanceof HTMLDetailsElement) || !sheet.classList.contains("sheet")) return;
      const summary = sheet.querySelector(":scope > summary");
      if (!(summary instanceof HTMLElement)) return;
      if (sheet.open) {
        summary.setAttribute("aria-label", "ปิดแผงนี้");
        const first = sheet.querySelector<HTMLElement>(":scope > .panel button, :scope > .panel a, :scope > .panel input, :scope > .panel textarea");
        first?.focus();
      } else {
        summary.removeAttribute("aria-label");
        summary.focus();
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const open = document.querySelector<HTMLDetailsElement>("details.sheet[open]");
      if (open) open.open = false;
    };
    document.addEventListener("toggle", onToggle, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("toggle", onToggle, true);
      document.removeEventListener("keydown", onKey);
    };
  }, []);
  return null;
}
