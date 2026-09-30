import Link from "next/link";

/**
 * An address nobody made. Next's own page is English ("This page could not be
 * found"). An order or a draft that is not there is answered by its own screen
 * (`NotThere`), not here.
 */
export default function NotFound() {
  return (
    <main>
      <section className="card">
        <h1>ไม่พบหน้านี้</h1>
        <p>ไม่มีหน้านี้ในระบบ อาจพิมพ์ที่อยู่ผิด หรือเป็นลิงก์เก่า</p>
        <Link className="button-link quiet" href="/">
          กลับหน้าแรก
        </Link>
      </section>
    </main>
  );
}
