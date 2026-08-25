/**
 * The one refusal in this API that answers with data rather than a sentence.
 *
 * Its own module, with no imports at all, for two reasons: `node --test` does
 * not resolve the `@/` alias, so a helper that lives beside a `fetch` cannot be
 * unit tested here; and the shape is a contract between two services - the
 * screen offers "this is something else" and that button has to carry the
 * references the person was actually shown (ADR-077 section 3).
 */
export function openOrdersIn(body: unknown): string[] {
  if (typeof body !== "object" || body === null) return [];
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) return [];
  const open = (detail as { open_orders?: unknown }).open_orders;
  if (!Array.isArray(open)) return [];
  return open.filter((ref): ref is string => typeof ref === "string");
}
