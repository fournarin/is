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

/**
 * Each open ticket as machine and symptom, aligned with `openOrdersIn`: one
 * short line each, where the full reasons ran together into one paragraph
 * (fourth trial, finding 20).
 */
export function openTitlesIn(body: unknown): string[] {
  if (typeof body !== "object" || body === null) return [];
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) return [];
  const titles = (detail as { open_titles?: unknown }).open_titles;
  if (!Array.isArray(titles)) return [];
  return titles.map((one) => (typeof one === "string" ? one : ""));
}

/** What each open ticket is about, aligned with `openOrdersIn` (ADR-126). */
export function openReasonsIn(body: unknown): string[] {
  if (typeof body !== "object" || body === null) return [];
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) return [];
  const reasons = (detail as { open_reasons?: unknown }).open_reasons;
  if (!Array.isArray(reasons)) return [];
  return reasons.map((one) => (typeof one === "string" ? one : ""));
}
