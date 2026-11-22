/**
 * Where a line of Thai may break, so it never breaks inside a word.
 *
 * Thai has no spaces between words and Chrome breaks it with a dictionary that
 * splits plant compounds a technician reads as one word: "ของตัว | เอง",
 * "หัวหน้า | กะ", "R- | 2000iC" (GATE 1 review, design/system README). The
 * segmenter here is the same dictionary, run on the server; the glossary then
 * vetoes the splits inside compounds, and codes and number + unit stay whole.
 * The screen wraps each piece in a nowrap span, so a line can only break
 * between pieces. No imports, so `node --test` can run it.
 */

// Compounds the dictionary splits but the floor reads as one word. A screen
// that shows a new one badly adds it here.
const COMPOUNDS = [
  "ของตัวเอง", "ตัวเอง", "เกินกำหนด", "ติดตั้งหลังคา", "ความแข็งแรง", "เชื่อมเสริม", "คาดว่าจะเกิน",
  "ควบคุมหุ่นยนต์", "หุ่นยนต์", "คลาดเคลื่อน", "ล็อกเอาต์", "ตัวถัง", "เกินเกณฑ์", "ถึงเกณฑ์",
  "พลังงาน", "ไม่พบอาการ", "ซ่อมชั่วคราว", "กุญแจล็อก", "ตู้ควบคุม", "มอเตอร์", "สายพาน",
  "ทำความสะอาด", "ไม่ตอบสนอง", "ตอบสนอง", "หัวหน้ากะ", "ช่างไฟฟ้า", "ไฮดรอลิก", "แนวโน้ม",
  "ระบายความร้อน", "ฝาครอบ", "ทดลองเดิน", "กลิ่นไหม้", "ไฟเตือน", "น้ำมันซึม", "ช้ากว่ากำหนด",
  "บำรุงรักษา", "ใบงาน", "เบรกเกอร์", "หยุดฉุกเฉิน", "ตะแกรง", "ตรวจขนาด", "ด้านข้าง",
  "ติดตั้งประตู", "ซีลตะเข็บ", "ประจำสถานี", "สายประกอบ", "จาระบี", "ชุดเกียร์", "สายเคเบิล",
  "ตามแผน", "นาทีว่าง", "ต่ำกว่า", "ผิดปกติ", "เครื่องหยุด", "ปลดกุญแจ", "ใส่กุญแจ", "ล็อกนิรภัย",
  "คอขวด", "อ้างถึง", "กะเช้า", "กะบ่าย", "กะดึก", "ขั้นตอน", "คู่มือ", "วิศวกร", "สกรู",
];

// Pieces that never break inside: codes, model names, number + unit.
const KEEP =
  /(Wi-Fi|R-\d+\w*|M-\d+\w*|MC-\d+|WO-\d+|CP-\d+|TP-\d+|SYM-\d+|M\d+|J\d|ก-\d+|\d[\d,.:]*\s?(?:N·m|Nm|°C|มม\.|นาที|คัน|วัน|ชม\.|น\.|ใบ|คน|ขั้น|ครั้ง)|±\s?\d+\s?ชม\.|\d+\s(?:ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.)(?:\s\d{4})?)/g;
const THAI = /[฀-๿]/;
const COMPOUND = new RegExp(
  [...COMPOUNDS].sort((a, b) => b.length - a.length).join("|"),
  "g",
);
const segmenter = new Intl.Segmenter("th", { granularity: "word" });

/**
 * The text cut into pieces that may each sit at the start of a line.
 *
 * Joined back together they are exactly the input: nothing is added, removed or
 * reordered, which is what lets a screen check still read the sentence.
 */
export function thaiPieces(text: string): string[] {
  if (!THAI.test(text) && !KEEP.test(text)) {
    KEEP.lastIndex = 0;
    return [text];
  }
  KEEP.lastIndex = 0;
  const cuts = new Set<number>();
  let at = 0;
  for (const { segment } of segmenter.segment(text)) {
    at += segment.length;
    cuts.add(at);
  }
  for (const pattern of [COMPOUND, KEEP]) {
    pattern.lastIndex = 0;
    for (const match of text.matchAll(pattern)) {
      for (let inside = match.index + 1; inside < match.index + match[0].length; inside++) {
        cuts.delete(inside);
      }
    }
  }
  // "ๆ" never starts a line.
  for (let index = 0; index < text.length; index++) {
    if (text[index] === "ๆ") {
      cuts.delete(index);
      if (text[index - 1] === " ") cuts.delete(index - 1); // "อื่น ๆ" stays on one line
    }
  }
  const pieces: string[] = [];
  let start = 0;
  for (const cut of [...cuts].sort((a, b) => a - b)) {
    if (cut > start) pieces.push(text.slice(start, cut));
    start = cut;
  }
  if (start < text.length) pieces.push(text.slice(start));
  return pieces;
}
