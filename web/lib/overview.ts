/**
 * The three overview endpoints, as this screen reads them.
 *
 * Nothing here computes a summary. ADR-063 and ADR-050 both say the same thing
 * from different sides: what is shown is what a round already decided, and a
 * screen that added its own aggregate would be a second opinion about a shift
 * that nobody could reconcile with the first.
 */
import { callApi } from "@/lib/api";

export type StationState = "normal" | "predicted" | "over_threshold";

export type Station = {
  station_id: string;
  seq: number;
  buffer_units: number;
  buffer_minutes: number;
  bottleneck: boolean;
  bottleneck_multiplier: number;
  machines: string[];
  state: StationState;
  machine_id: string | null;
  component: string | null;
  symptom_code: string | null;
  // The symptom as the plant names it (ADR-093).
  symptom_title: string | null;
  severity: string | null;
  rule_id: string | null;
  live_findings: number;
  over_threshold_minutes: number | null;
  eta: string | null;
  eta_confidence_minutes: number | null;
};

export type Line = {
  line_id: string;
  takt_seconds: number;
  stations: Station[];
};

export type ShiftBand = {
  shift_id: string | null;
  on_date: string | null;
  band: string;
  load_ratio: number | null;
  capacity_minutes: number;
  committed_minutes: number;
  technicians_on_shift: number;
  open_orders: number;
  held: number;
  summary: string;
};

export type LineOverview = {
  at: string;
  timezone: string;
  lines: Line[];
  shift: ShiftBand;
  unplaced_machines: string[];
};

export type SymptomGap = {
  symptom_code: string;
  title: string | null;
  machine_model: string;
  findings: number;
  occurrences: number;
  machines: string[];
  first_seen: string;
  last_seen: string;
  proposals_waiting: number;
};

export type ModelQueue = {
  machine_model: string;
  waiting: number;
  oldest: string;
};

export type FlaggedPlaybook = {
  title: string | null;
  symptom_code: string;
  machine_model: string;
  revision: number;
  review_reason: string | null;
};

export type Gaps = {
  at: string;
  no_playbook: { count: number; rows: SymptomGap[] };
  awaiting_review: { count: number; rows: ModelQueue[] };
  manual_changed: { count: number; rows: FlaggedPlaybook[] };
};

async function read<T>(path: string): Promise<T> {
  const response = await callApi(path);
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

export async function lineOverview(): Promise<LineOverview> {
  return read<LineOverview>("/overview/line");
}

export async function gaps(): Promise<Gaps> {
  return read<Gaps>("/overview/gaps");
}

export type HistoryContribution = {
  observed_from: string | null;
  observed_to: string | null;
  observed_days: number;
  closed_orders: number;
  failures: number;
  failures_per_100_days: number | null;
  last_failure_at: string | null;
  days_since_last_failure: number | null;
  pm_completed: number;
  pm_overdue: number;
  pm_overdue_days: number | null;
  false_alarms: number;
  absent: string[];
  reason: string;
};

export type CurrentContribution = {
  open_findings: number;
  acknowledged: number;
  detected: number;
  predicted: number;
  highest_severity: string | null;
  soonest_eta: string | null;
  hours_to_soonest_eta: number | null;
  reason: string;
};

export type MachineHealth = {
  machine_id: string;
  history: HistoryContribution;
  now: CurrentContribution;
};

/**
 * Two orderings of the same machines, and deliberately no third figure.
 *
 * There is no `score` here and adding one would mean adding it to the response
 * model first, which is a file that says not to (ADR-072 section 2, ADR-081).
 */
export type MachineHealthOverview = {
  at: string;
  observed_from: string | null;
  observed_to: string | null;
  observed_days: number;
  by_history: MachineHealth[];
  by_now: MachineHealth[];
  absent: string[];
  unplaced_machines: string[];
};

export async function machineHealth(): Promise<MachineHealthOverview> {
  return read<MachineHealthOverview>("/overview/health");
}
