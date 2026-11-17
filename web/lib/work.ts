/**
 * What the technician's screen reads, and where each figure comes from.
 *
 * Two sources, deliberately: `/work-orders/mine` says which jobs are this
 * person's and in what order (layer 3 decided that, and this app does not
 * re-sort it), and the ticket says everything about one job. Nothing here
 * computes a priority, a duration or a reason - every sentence on the screen was
 * written by the backend, because a screen that phrases its own explanation is a
 * second opinion nobody approved (ADR-005).
 *
 * `myWork` used to filter `round.placed`, and that was wrong in a way only the
 * shipped stack could show (ADR-071 §7): `/dispatch/round` computes what a round
 * *would* decide, and `dispatch()` places only work that is still queued - so a
 * job left the list at the instant a round wrote it. The rehearsal stops
 * `worker-runtime` while the screen checks run, so every check saw a queue no
 * round had touched.
 */
import { callApi } from "@/lib/api";

export type Ranked = {
  ref: string;
  priority_score: number;
  priority_reason: string;
  assignees: string[];
  downtime_units: number;
  waited_minutes: number;
};

export type Round = {
  at: string;
  timezone: string;
  shift_id: string | null;
  on_date: string | null;
  band: string;
  load_ratio: number | null;
  capacity_minutes: number;
  committed_minutes: number;
  summary: string;
  placed: Ranked[];
  unassigned: { ref: string; why: string }[];
  held: { ref: string; why: string }[];
  // What the shift lead set aside this shift, with their reason (ADR-120).
  set_aside: { ref: string; why: string }[];
};

export type Step = {
  text: string;
  text_th: string | null;
  source_doc: string;
  page: number;
  manual: string | null;
  // As the approving engineer marked it (ADR-135); absent on older tickets.
  kind?: StepKind;
  hazards?: string[];
  isolation_points?: IsolationPoint[];
  wait_minutes?: number | null;
};

export type StepKind = "normal" | "isolation" | "verify" | "restore" | "hazard";
export type IsolationPoint = { point_id: string; label: string; energy: string };
export type PointConfirmed = { step: number; point_id: string; item: string; by: string; at: string };
export type LockOn = {
  point_id: string;
  lock_no: string;
  owner: string;
  owner_name: string;
  work_order_ref: string;
  step: number;
  applied_at: string;
};

export type Recurrence = {
  occurrence_count: number;
  detected_at: string;
  last_seen_at: string | null;
  status: string;
};

export type WhereToLook = {
  document_id: string;
  manual: string;
  page: number | null;
  from_unapproved_draft: boolean;
};

export type Ticket = {
  ref: string;
  machine_id: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "queued" | "assigned" | "in_progress" | "handed_over" | "closed" | "cancelled";
  origin: "condition" | "scheduled" | "manual";
  // Machine and symptom, as the floor names the job (fourth trial).
  title?: string;
  reason: string;
  // Other work open on this machine as the ticket was read (finding 5).
  also_open?: string[];
  priority_reason: string;
  priority_score: number;
  estimated_minutes: number;
  estimate_is_fallback: boolean;
  required_skill: string | null;
  required_skill_name: string | null;
  station: string | null;
  tools: string[];
  // The approver's Thai for each tool; "" where the manual's words stand (ADR-130).
  tools_th?: string[];
  required_technicians: number;
  assignees: string[];
  playbook_warning: string | null;
  // How far the last person got before putting the job down (ADR-025, ADR-120).
  handover_note: string | null;
  finding_kind: "detected" | "predicted" | null;
  eta: string | null;
  eta_confidence_minutes: number | null;
  // The live forecast with its interval, as the backend wrote it (ADR-123).
  eta_text: string | null;
  steps: Step[];
  // Filled only when `steps` is empty (ADR-118).
  where_to_look?: WhereToLook[];
  // A scheduled job with no steps: which part of the manual, and that no page
  // is on record (fourth trial, finding 11).
  where_to_look_note?: string | null;
  recurrence: Recurrence | null;
  // What the job page shows besides the steps (ADR-134).
  station_name?: string | null;
  machine_model?: string | null;
  started_at?: string | null;
  step_reached?: number | null;
  reading?: Reading | null;
  history?: PastJob[];
  approval?: Approval | null;
  engineer?: string | null;
  // Isolation, point by point (ADR-135).
  confirmations?: PointConfirmed[];
  locks?: LockOn[];
  your_lock_numbers?: string[];
  missing_verify?: boolean;
  unverified_points?: string[];
  restore_checks?: { key: string; label: string }[];
};

/** The measurement behind a condition ticket, as its Finding recorded it. */
export type Reading = {
  metric_name: string;
  metric_title: string | null;
  unit: string | null;
  value: number | null;
  measured_at: string | null;
  threshold: number | null;
  comparison: string | null;
  slope_per_hour: number | null;
};

/** One closed job on the same machine. */
export type PastJob = {
  ref: string;
  title: string;
  closed_at: string;
  outcome: "fixed" | "temporary_fix" | "not_fixed" | "no_problem_found";
  minutes: number;
  by: string[];
  page: number | null;
  note: string | null;
};

export type Approval = {
  approved_by: string;
  approved_at: string;
  revision: number | null;
  manual: string | null;
};

export type Lamp = { seq: number; name: string | null; state: "normal" | "predicted" | "over_threshold" };

export type MyLock = {
  lock_id: number;
  job_open: boolean;
  checks_needed: { key: string; label: string }[];
  work_order_ref: string;
  machine_id: string;
  point_id: string;
  lock_no: string;
  step: number;
  applied_at: string;
};

/** The reader's own locks still on, on any job (ADR-136); empty when it cannot be read. */
export async function myLocks(): Promise<MyLock[]> {
  try {
    return await read<MyLock[]>("/locks/mine");
  } catch {
    return [];
  }
}

/** Every station's lamp, for the sign over a job (ADR-134). Null when it cannot be read: the sign then has no strip. */
export async function lineLamps(): Promise<Lamp[][] | null> {
  try {
    return (await read<{ lines: Lamp[][] }>("/line/lamps")).lines;
  } catch {
    return null;
  }
}

async function read<T>(path: string): Promise<T> {
  const response = await callApi(path);
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

export async function currentRound(): Promise<Round> {
  return read<Round>("/dispatch/round");
}

export async function ticket(ref: string): Promise<Ticket> {
  return read<Ticket>(`/work-orders/${encodeURIComponent(ref)}`);
}

/**
 * The ticket behind a link somebody followed, or null when there is none.
 *
 * A kept or mistyped link names an order that is not there, and the API's 404
 * used to surface as the "cannot connect, try again" page (2026-09-30). Null
 * rather than `notFound()`: that answer is drawn by the browser's script, and a
 * phone whose bundle never arrived would be shown an empty page.
 */
export async function ticketAt(ref: string): Promise<Ticket | null> {
  const path = `/work-orders/${encodeURIComponent(ref)}`;
  const response = await callApi(path);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for ${path}`);
  }
  return (await response.json()) as Ticket;
}

export type Mine = {
  ref: string;
  status: Ticket["status"];
  priority_score: number;
  priority_reason: string;
};

export type Proposal = {
  ref: string;
  proposed_at: string;
  assignees: string[];
  assignee_names: string[];
  priority_score: number;
  priority_reason: string;
  band: string | null;
  load_ratio: number | null;
  shift_id: string | null;
  expires_at: string;
  // Who else on this shift could take it, for "ให้คนอื่น" (ADR-132).
  others: { user: string; name: string }[];
  // Cars lost if it waits, and why this person, both from the API (ADR-141).
  downtime_units?: number | null;
  assigned_because?: string | null;
};

/**
 * This person's jobs, in the order the scheduler put them in.
 *
 * The list arrives ranked by the `priority_score` layer 3 froze onto each order
 * when it placed it, and is passed through untouched. Re-sorting it here - by
 * severity, by machine, by anything - would quietly replace layer 3's answer
 * with this file's opinion, and the whole argument for a load gate is that the
 * order is not negotiable at the edges (ADR-011).
 *
 * The endpoint always answers about the caller, so there is no user to pass and
 * nothing a wrong argument here could reveal.
 */
export async function myWork(): Promise<Ticket[]> {
  const mine = await read<Mine[]>("/work-orders/mine");
  return Promise.all(mine.map((one) => ticket(one.ref)));
}

/** What the scheduler is waiting to be told about (ADR-071). */
export async function proposals(): Promise<Proposal[]> {
  return read<Proposal[]>("/dispatch/proposals");
}

export type Active = {
  ref: string;
  machine_id: string;
  status: Ticket["status"];
  assignees: string[];
  assignee_names: string[];
  reason: string;
  eta_text: string | null;
};

/** What the floor is on right now, for the shift lead's board (ADR-093). */
export async function activeWork(): Promise<Active[]> {
  return read<Active[]>("/work-orders/active");
}

/** A job closed this shift, as the board's last column shows it (ADR-126). */
export type Finished = {
  ref: string;
  machine_id: string;
  reason: string;
  closed_when: string;
  outcome: string;
  by_names: string[];
  note: string | null;
};

export async function finishedThisShift(): Promise<Finished[]> {
  return read<Finished[]>("/work-orders/finished");
}

/** Each tool in the approver's Thai where there is one, else as the manual wrote it. */
export function toolNames(job: { tools: string[]; tools_th?: string[] }): string[] {
  return job.tools.map((tool, index) => job.tools_th?.[index] || tool);
}
