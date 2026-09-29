"use client";

import Link from "next/link";

/**
 * What any screen shows when it cannot be drawn - most often because the API
 * did not answer. Before this, a person got Next's English "A server error
 * occurred" with a digest number (2026-09-29).
 *
 * A server error's message does not reach the browser in production, so this
 * page cannot say which failure it was. It says what is true of all of them and
 * what to do next.
 */
export default function ScreenError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main>
      <section className="card" role="alert">
        <h1>เชื่อมต่อระบบไม่ได้ชั่วคราว</h1>
        <p>หน้านี้โหลดไม่สำเร็จ ระบบอาจกำลังเริ่มใหม่ รอสักครู่แล้วกดลองใหม่</p>
        <p className="muted">
          การปิดงานที่เก็บไว้ในเครื่องไม่หาย จะส่งเองเมื่อระบบกลับมา ถ้ารอไม่ได้ ให้โทรหาหัวหน้ากะ
        </p>
        <button type="button" onClick={reset}>
          ลองใหม่
        </button>{" "}
        <Link className="button-link quiet" href="/">
          กลับหน้าแรก
        </Link>
      </section>
    </main>
  );
}
