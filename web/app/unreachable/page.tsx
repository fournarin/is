import Link from "next/link";

/**
 * Where a signed-in screen sends a person when the API does not answer.
 *
 * Asks nothing of the API, so it always renders, and needs no JavaScript.
 */
export default function UnreachablePage() {
  return (
    <main>
      <section className="card" role="alert" style={{ marginTop: "12vh" }}>
        <h1>เชื่อมต่อระบบไม่ได้ชั่วคราว</h1>
        <p>ระบบอาจกำลังเริ่มใหม่ รอสักครู่แล้วกดลองใหม่</p>
        <p className="muted">
          การปิดงานที่เก็บไว้ในเครื่องไม่หาย จะส่งเองเมื่อระบบกลับมา ถ้ารอไม่ได้ ให้โทรหาหัวหน้ากะ
        </p>
        <Link className="button-link" href="/">
          ลองใหม่
        </Link>
      </section>
    </main>
  );
}
