/**
 * What the improvement-loop screen reads (ADR-087).
 *
 * Two reads and no opinion about either. The API computes both loops when asked
 * and stores nothing, so what this screen shows is what the closed work says at
 * the moment somebody opened it. Nothing here re-ranks or re-words: the reason
 * sentence on every proposal is written by the loop that made it, where it can
 * be tested without a browser (ADR-066, ADR-073).
 *
 * There is nothing to post. Loop 1's number lives on a playbook row that carries
 * an engineer's approval and Loop 2's lives in `config/rules.yaml`; both are
 * carried across by a person, and the API has no route that would do it for them.
 */
import { callApi } from "@/lib/api";

export type EstimateProposal = {
  symptom_code: string;
  machine_model: string;
  current_minutes: number;
  proposed_minutes: number;
  median_minutes: number;
  capped: boolean;
  observations: number;
  shortest_minutes: number;
  longest_minutes: number;
  evidence: string[];
  no_problem_found: number;
  without_repair_time: number;
  reason: string;
};

export type EstimateLine = {
  symptom_code: string;
  machine_model: string;
  current_minutes: number;
  playbook_status: string;
  closed_orders: number;
  proposal: EstimateProposal | null;
};

export type ThresholdProposal = {
  rule_id: string;
  comparison: string;
  current_threshold: number;
  proposed_threshold: number;
  separating_threshold: number;
  capped: boolean;
  observations: number;
  false_alarms: number;
  faults_found: number;
  excluded_predictions: number;
  would_not_have_fired: string[];
  still_fires_on: string[];
  reason: string;
  limitation: string;
};

export type NoProposal = {
  rule_id: string;
  cause: string;
  observations: number;
  false_alarms: number;
  faults_found: number;
  excluded_predictions: number;
  reason: string;
};

export type ThresholdLine = {
  rule_id: string;
  machine_model: string;
  metric_name: string;
  comparison: string;
  current_threshold: number;
  safety_critical: boolean;
  without_a_reading: number;
  proposal: ThresholdProposal | null;
  refusal: NoProposal | null;
};

async function read<T>(path: string): Promise<T> {
  const response = await callApi(path);
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

export async function estimateProposals(): Promise<EstimateLine[]> {
  return read<EstimateLine[]>("/loops/estimates");
}

export async function thresholdProposals(): Promise<ThresholdLine[]> {
  return read<ThresholdLine[]>("/loops/thresholds");
}
