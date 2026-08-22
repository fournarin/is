/**
 * What a reviewer cannot see unaided, worked out from the draft itself.
 *
 * Three judgements, and no I/O of any kind - which is why they are here rather
 * than in `review.ts` beside the reads. They are the part of this screen that
 * can be wrong without anybody noticing, so they are the part that is tested
 * (`drafts.test.ts`), and a module that imported the API could not be tested
 * without one:
 *
 *  - which model's queue a proposal belongs in, so a reviewer stays in one
 *    context rather than alternating between two manuals (ADR-064);
 *  - which step cites a different document from the rest of the draft, because
 *    authoring is tuned for recall (ADR-015) and a mixed draft looks perfectly
 *    ordinary at page level;
 *  - where in the cited page the drafted step came from, so a decision takes
 *    seconds rather than a PDF.
 *
 * The types the API answers with live here too, for the same reason: a type is
 * what the test builds its fixtures from.
 */

/** One line of `/playbooks/queue` (src/pdm/api/playbooks.py). */
export type QueuedProposal = {
  proposal_id: number;
  symptom_code: string;
  machine_model: string;
  origin: "drafted" | "technician";
  outcome: string;
  steps: number;
  rejected: number;
  reason: string;
  created_at: string;
  created_by: string | null;
};

export type DraftStep = {
  text: string;
  source_doc: string;
  page: number;
  confidence: number;
};

/**
 * `/playbooks/queue/{id}`.
 *
 * There is no timing field on it and that is deliberate on the API's side: the
 * time a review took is recorded and never sent to a screen, because a visible
 * clock pressures somebody reviewing safety-critical text into hurrying
 * (ADR-064). This type is the shape of that decision - there is nothing here a
 * timer could be rendered from.
 */
export type Proposal = {
  proposal_id: number;
  symptom_code: string;
  machine_model: string;
  origin: "drafted" | "technician";
  outcome: string;
  status: string;
  reason: string;
  steps: DraftStep[];
  tools: string[];
  proposed_skill: string | null;
  proposed_minutes: number | null;
  rejected: Record<string, unknown>[];
  created_at: string;
  created_by: string | null;
};

/** `/documents/{id}/pages/{page}` - the panel on the right. */
export type PageEvidence = {
  document_id: string;
  title: string;
  machine_model: string;
  edition: string | null;
  withdrawn: boolean;
  page: number;
  outcome: string;
  text: string | null;
};

export type ModelQueue = {
  machine_model: string;
  proposals: QueuedProposal[];
};

/**
 * The queue as a reviewer meets it: one machine model at a time.
 *
 * Grouped rather than sorted, because the cost being avoided is not scrolling -
 * it is context. Reviewing an R-2000iC draft against an M-710iC one alternately
 * means holding two manuals in mind, and that is where "wrong model" gets
 * approved.
 *
 * The order within a group is the order the API sent (oldest first), and the
 * groups themselves are ordered by their oldest proposal: the model nobody has
 * looked at for three weeks is named first, not the one whose name sorts first.
 * Same rule as `/overview/gaps` uses for the same list (ADR-060).
 */
export function groupByModel(queue: readonly QueuedProposal[]): ModelQueue[] {
  const groups = new Map<string, QueuedProposal[]>();
  for (const item of queue) {
    const held = groups.get(item.machine_model);
    if (held === undefined) {
      groups.set(item.machine_model, [item]);
      continue;
    }
    held.push(item);
  }
  return [...groups.entries()]
    .map(([machine_model, proposals]) => ({ machine_model, proposals }))
    .sort((left, right) => {
      const oldest = left.proposals[0].created_at.localeCompare(right.proposals[0].created_at);
      return oldest !== 0 ? oldest : left.machine_model.localeCompare(right.machine_model);
    });
}

export type FlaggedStep = DraftStep & {
  /**
   * True when this step cites a document the rest of the draft does not.
   *
   * "The rest" and not "the previous one": a draft of three steps where the
   * second comes from elsewhere should flag the second, and a rule comparing
   * neighbours would flag the third as well and leave a reviewer working out
   * which of the two is the odd one.
   */
  odd_document: boolean;
};

/**
 * The steps with the one that came from somewhere else marked.
 *
 * The majority document is the draft's own, and anything else stands out. When
 * a draft cites two documents equally - two steps each - every step is flagged,
 * which is the honest answer: there is no majority, and the reviewer is being
 * shown a procedure assembled from two manuals.
 */
export function flagSteps(steps: readonly DraftStep[]): FlaggedStep[] {
  const counted = new Map<string, number>();
  for (const step of steps) {
    counted.set(step.source_doc, (counted.get(step.source_doc) ?? 0) + 1);
  }
  const most = Math.max(0, ...counted.values());
  const majority = [...counted.entries()].filter(([, count]) => count === most);
  const home = majority.length === 1 ? majority[0][0] : null;
  return steps.map((step) => ({ ...step, odd_document: step.source_doc !== home }));
}

export type Located = { before: string; match: string; after: string };

/**
 * Where in the page the step was taken from, for the highlight.
 *
 * ADR-037 makes this possible at all: a drafting backend selects spans and the
 * service checks that each step's text is contained in the chunk it cites, once
 * whitespace and a leading step number are normalised away. So the same
 * normalisation is what finds it again here - and when it does not, the panel
 * says so rather than highlighting the nearest thing it can find, which would be
 * this screen inventing evidence.
 */
export function locate(page: string, step: string): Located | null {
  const needle = normalise(step);
  if (needle === "") {
    return null;
  }
  // The page with each character's position in the original kept beside it, so
  // a match found in normalised text can be cut out of the text a person reads.
  const flat: string[] = [];
  const at: number[] = [];
  let space = false;
  for (let index = 0; index < page.length; index += 1) {
    const character = page[index];
    if (/\s/.test(character)) {
      space = true;
      continue;
    }
    if (space && flat.length > 0) {
      flat.push(" ");
      at.push(index);
    }
    space = false;
    flat.push(character.toLowerCase());
    at.push(index);
  }

  const found = flat.join("").indexOf(needle);
  if (found === -1) {
    return null;
  }
  const start = at[found];
  const end = at[found + needle.length - 1] + 1;
  return { before: page.slice(0, start), match: page.slice(start, end), after: page.slice(end) };
}

/** Whitespace collapsed, case dropped, a leading "3." or "3)" removed. */
function normalise(text: string): string {
  return text
    .replace(/^\s*\d+\s*[.)]\s*/, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}
