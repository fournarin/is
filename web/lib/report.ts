/**
 * What the report screen reads: the machines somebody can point at.
 *
 * One reader, and it is a list of what is on the floor rather than anything
 * about work. A free-text machine number on a phone at a machine collects
 * typos and answers them with a 422, which is a bad conversation to have while
 * standing next to something that is broken (ADR-077).
 */
import { callApi } from "@/lib/api";

export type Machine = {
  machine_id: string;
  model: string;
  station_id: string;
  line_id: string;
  seq: number;
  /** The floor's name for the station, when plant.yaml gives one (REQ-P-03). */
  station_name?: string | null;
};

export async function machines(): Promise<Machine[]> {
  const response = await callApi("/machines");
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for /machines`);
  }
  return (await response.json()) as Machine[];
}

/** One fault this person reported, and where it is now (ADR-122). */
export type Reported = {
  ref: string;
  machine_id: string;
  reported_at: string;
  reported_when: string;
  reason: string;
  // What the reporter wrote, so two reports on one machine differ (finding 19).
  what?: string;
  status: string;
  where: string;
  finished: boolean;
  /** The four stages and which one this is (REQ-P-05). `where` names people and the operator never sees it (REQ-P-06). */
  stages?: string[];
  stage?: number;
  /** A photo was kept with it (ADR-142). */
  photo?: boolean;
};

export async function myReports(): Promise<Reported[]> {
  const response = await callApi("/work-orders/reported");
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for /work-orders/reported`);
  }
  return (await response.json()) as Reported[];
}
