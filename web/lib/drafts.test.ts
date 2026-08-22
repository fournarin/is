/**
 * The three judgements the review screen makes, without a browser.
 *
 * `node --test` runs TypeScript directly on Node 24, so this needs no test
 * framework and no new dependency (CLAUDE.md).
 *
 * The middle one is the reason this file exists. Slice 10.2 asks that a step
 * citing a different document than its neighbours is *asserted in a test, not
 * left to the eye* - because leaving it to the eye is exactly what fails: at
 * page level a mixed draft looks ordinary, and ADR-015's recall setting makes
 * mixed drafts an ordinary outcome rather than a rare one.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type DraftStep,
  type QueuedProposal,
  flagSteps,
  groupByModel,
  locate,
} from "./drafts.ts";

const MANUAL = "a".repeat(64);
const OTHER = "b".repeat(64);

function step(text: string, source_doc = MANUAL, page = 142): DraftStep {
  return { text, source_doc, page, confidence: 0.8 };
}

function queued(
  proposal_id: number,
  machine_model: string,
  created_at: string,
): QueuedProposal {
  return {
    proposal_id,
    symptom_code: `SYM-0${proposal_id}`,
    machine_model,
    origin: "drafted",
    outcome: "repair",
    steps: 3,
    rejected: 0,
    reason: "3 steps",
    created_at,
    created_by: null,
  };
}

test("the queue is grouped by machine model, oldest queue first", () => {
  const groups = groupByModel([
    queued(1, "M-710iC", "2026-03-03T09:00:00Z"),
    queued(2, "R-2000iC", "2026-03-01T09:00:00Z"),
    queued(3, "M-710iC", "2026-03-04T09:00:00Z"),
  ]);

  assert.deepEqual(
    groups.map((group) => group.machine_model),
    ["R-2000iC", "M-710iC"],
  );
  assert.deepEqual(
    groups[1].proposals.map((one) => one.proposal_id),
    [1, 3],
  );
});

test("the order the API sent is kept inside a group", () => {
  const groups = groupByModel([
    queued(1, "R-2000iC", "2026-03-01T09:00:00Z"),
    queued(2, "R-2000iC", "2026-03-02T09:00:00Z"),
  ]);

  assert.deepEqual(
    groups[0].proposals.map((one) => one.proposal_id),
    [1, 2],
  );
});

test("a draft from one manual flags nothing", () => {
  const flagged = flagSteps([step("Stop the robot."), step("Lock out CP-3.")]);

  assert.deepEqual(
    flagged.map((one) => one.odd_document),
    [false, false],
  );
});

test("the one step from another document is the one flagged", () => {
  const flagged = flagSteps([
    step("Stop the robot."),
    step("Lock out CP-3."),
    step("Remove the fan cover.", OTHER, 88),
  ]);

  assert.deepEqual(
    flagged.map((one) => one.odd_document),
    [false, false, true],
  );
});

test("a step in the middle is flagged, and the one after it is not", () => {
  // The rule is "against the rest of the draft", not "against the previous
  // step": comparing neighbours would flag step 3 as well and leave a reviewer
  // working out which of the two is the odd one.
  const flagged = flagSteps([
    step("Stop the robot."),
    step("Consult the safety bulletin.", OTHER, 2),
    step("Lock out CP-3."),
  ]);

  assert.deepEqual(
    flagged.map((one) => one.odd_document),
    [false, true, false],
  );
});

test("two manuals in equal measure flags every step", () => {
  // There is no majority to be the draft's home, and saying so is honest: this
  // is a procedure assembled from two manuals, which is the thing ADR-015 says
  // reviewers cannot spot unaided.
  const flagged = flagSteps([
    step("Stop the robot."),
    step("Consult the safety bulletin.", OTHER, 2),
  ]);

  assert.deepEqual(
    flagged.map((one) => one.odd_document),
    [true, true],
  );
});

const PAGE =
  "5.2 Motor replacement\nStop the robot using the  emergency stop button, then apply\nlockout per the site procedure.";

test("the span is found across the line breaks the page has and the step does not", () => {
  const found = locate(PAGE, "Stop the robot using the emergency stop button");

  assert.notEqual(found, null);
  assert.equal(found?.match, "Stop the robot using the  emergency stop button");
  assert.ok(found?.before.endsWith("replacement\n"));
  assert.ok(found?.after.startsWith(", then apply"));
});

test("a leading step number does not stop the span being found", () => {
  // ADR-037's containment check normalises one away, so the screen has to as
  // well or it would fail to highlight text the backend proved is there.
  const found = locate(PAGE, "3. Stop the robot using the emergency stop button");

  assert.equal(found?.match, "Stop the robot using the  emergency stop button");
});

test("what is not on the page is reported as not found, never approximated", () => {
  // The alternative is highlighting the nearest thing, which is the screen
  // inventing evidence for a step the manual does not carry.
  assert.equal(locate(PAGE, "Torque the bolts to 42 Nm."), null);
});

test("putting the pieces back together gives the page unchanged", () => {
  const found = locate(PAGE, "apply lockout per the site procedure.");

  assert.equal(`${found?.before}${found?.match}${found?.after}`, PAGE);
});
