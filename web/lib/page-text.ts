/**
 * A manual page's indexed text, back in the lines a person reads it in.
 *
 * The index keeps a page's first line break (after its heading) and paragraph
 * breaks, and joins the rest: a procedure arrives as "... 1. Isolate ... 2.
 * Remove ...", and the PDF's own wrap points arrive as single newlines in the
 * middle of sentences (fourth trial; set 1 review). This puts back only what
 * the text itself marks: a short first line with no full stop is the heading,
 * a numbered item starts a line after a sentence ends, and so does a label
 * sentence such as "Required tools:". Nothing is reworded or dropped.
 */
export function pageParagraphs(text: string): { heading: string | null; paragraphs: string[] } {
  let body = text.trim();
  let heading: string | null = null;
  const firstBreak = body.indexOf("\n");
  if (firstBreak > 0) {
    const first = body.slice(0, firstBreak).trim();
    if (first.length <= 80 && !/[.:;]$/.test(first)) {
      heading = first;
      body = body.slice(firstBreak + 1);
    }
  }
  const paragraphs = body
    .split(/\n{2,}/)
    .map((one) => one.replace(/\s*\n\s*/g, " ").trim())
    .flatMap((one) => one.split(/(?<=\.)\s+(?=\d{1,2}\.\s)|(?<=\.)\s+(?=[A-Z][a-z]+(?: [a-z]+){0,2}:\s)/))
    .map((one) => one.trim())
    .filter((one) => one !== "");
  return { heading, paragraphs };
}
