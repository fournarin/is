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
};

export async function machines(): Promise<Machine[]> {
  const response = await callApi("/machines");
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for /machines`);
  }
  return (await response.json()) as Machine[];
}
