"use client";

/**
 * "ปิด" at the top of a sheet's panel (Q13, ADR-139). Without a script the
 * dimmed backdrop above the panel closes it; with one, this button does too.
 */
export function SheetClose() {
  return (
    <button
      type="button"
      onClick={(event) => {
        const sheet = event.currentTarget.closest("details");
        if (sheet) sheet.open = false;
      }}
    >
      ปิด
    </button>
  );
}
