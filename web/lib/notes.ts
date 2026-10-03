/**
 * What technicians wrote when they closed a job (ADR-117).
 *
 * One read, newest first. Nothing here changes a playbook: a note that should
 * become a step goes through the review queue, which records who approved it.
 */
export type FloorNote = {
  work_order_ref: string;
  machine_id: string;
  symptom_code: string | null;
  // The plant's name for it (ADR-126); grouping stays on the code.
  symptom_title?: string | null;
  playbook_ref: string | null;
  outcome: string | null;
  closed_at: string;
  note: string;
};

export type FloorNotes = { timezone: string; notes: FloorNote[] };

/** Notes grouped by what they are about, the groups in order of their newest note. */
export function bySymptom(notes: readonly FloorNote[]): [string, FloorNote[]][] {
  const groups = new Map<string, FloorNote[]>();
  for (const one of notes) {
    const key = one.symptom_code ?? "ไม่ระบุอาการ";
    groups.set(key, [...(groups.get(key) ?? []), one]);
  }
  return [...groups.entries()];
}
