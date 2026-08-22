/**
 * The two overview endpoints, as this screen reads them.
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
  machine_model: string;
  findings: number;
  occurrences: number;
  machines: string[];
  first_seen: string;
  last_seen: string;
  proposals_waiting: number;
};

export type ModelQueue = { machine_model: string; waiting: number; oldest: string };

export type FlaggedPlaybook = {
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
