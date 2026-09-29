/** The read behind the notes screen (ADR-117). Kept apart from `notes.ts` so the
 * grouping there can be tested with `node --test`, which has no path aliases. */
import { callApi } from "@/lib/api";
import type { FloorNotes } from "@/lib/notes";

export async function floorNotes(): Promise<FloorNotes> {
  const response = await callApi("/loops/notes");
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for /loops/notes`);
  }
  return (await response.json()) as FloorNotes;
}
