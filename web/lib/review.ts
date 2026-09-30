/**
 * What the review screen reads. Three reads, and no opinion about any of them.
 *
 * The queue arrives ordered, the proposal arrives with its steps and their
 * citations, and the evidence arrives as the page text the drafter selected
 * from. Nothing here re-ranks, re-words or summarises: what a reviewer is shown
 * is what the API said, and the judgements this screen does make for itself are
 * in `drafts.ts`, where they can be tested without one.
 */
import { callApi } from "@/lib/api";

import type { PageEvidence, Proposal, QueuedProposal } from "@/lib/drafts";

async function read<T>(path: string): Promise<T> {
  const response = await callApi(path);
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

export async function reviewQueue(): Promise<QueuedProposal[]> {
  return read<QueuedProposal[]>("/playbooks/queue");
}

/** The proposal behind a link, or null when there is none (see `ticketAt`). */
export async function proposal(proposalId: number): Promise<Proposal | null> {
  const path = `/playbooks/queue/${proposalId}`;
  const response = await callApi(path);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for ${path}`);
  }
  return (await response.json()) as Proposal;
}

/**
 * The cited page, or null when there is nothing to show.
 *
 * A 404 is an ordinary answer here - the manual was never indexed, or the page
 * is outside what ingest read - and it is not the same thing as an error. The
 * screen says which of the two it is rather than showing an empty box
 * (principle 5).
 */
export async function evidence(documentId: string, page: number): Promise<PageEvidence | null> {
  const response = await callApi(`/documents/${encodeURIComponent(documentId)}/pages/${page}`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`the API answered ${response.status} for page ${page}`);
  }
  return (await response.json()) as PageEvidence;
}

