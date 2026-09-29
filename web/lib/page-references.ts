/**
 * The other pages a step names in its own words - "the lockout procedure on
 * page 2", "ดูหน้า 12" - so the step screen can open them, not only the page the
 * step was cited to.
 *
 * Read from the text rather than stored with the step: the manual's sentence is
 * the source, and the approver's Thai carries the same number (ADR-095 checks
 * that figures match), so reading both finds what either says.
 */

// A range longer than this is read as its two ends. "pages 1-400" is a table of
// contents, not a reference to four hundred pages.
const LONGEST_RANGE = 5;

const ENGLISH = /\b(?:pages?|p\.|pp\.)\s*(\d{1,4})(?:\s*(?:-|–|to|and)\s*(\d{1,4}))?/gi;
const THAI = /หน้า\s*(\d{1,4})(?:\s*(?:-|–|ถึง)\s*(\d{1,4}))?/g;

export function pagesNamed(text: string, cited: number): number[] {
  const found = new Set<number>();
  for (const pattern of [ENGLISH, THAI]) {
    for (const match of text.matchAll(pattern)) {
      const first = Number(match[1]);
      const last = match[2] === undefined ? first : Number(match[2]);
      if (last > first && last - first < LONGEST_RANGE) {
        for (let page = first; page <= last; page++) found.add(page);
      } else {
        found.add(first);
        if (last !== first) found.add(last);
      }
    }
  }
  found.delete(cited);
  return [...found].filter((page) => page > 0).sort((a, b) => a - b);
}
