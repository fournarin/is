/**
 * "Drawn to scale" is arithmetic, so it is tested as arithmetic - with two
 * different buffer maps, which is what slice 10.5 asks for. A screenshot cannot
 * tell a proportional diagram from a convincing one.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { HAIRLINE, edgeFractions, edgeWeights } from "./line-scale.ts";

const LINE_A = [
  { buffer_units: 20 },
  { buffer_units: 8 },
  { buffer_units: 0 },
  { buffer_units: 12 },
];

// The same line after somebody moves the bottleneck: every gap differs, so a
// diagram with fixed widths passes the first map and fails this one.
const LINE_B = [
  { buffer_units: 4 },
  { buffer_units: 30 },
  { buffer_units: 15 },
  { buffer_units: 1 },
];

test("there is one gap fewer than there are stations", () => {
  assert.equal(edgeWeights(LINE_A).length, LINE_A.length - 1);
  assert.deepEqual(edgeWeights([{ buffer_units: 5 }]), []);
  assert.deepEqual(edgeWeights([]), []);
});

test("each gap is the buffer of the station before it (ADR-063 section 4)", () => {
  assert.deepEqual(edgeWeights(LINE_A), [20, 8, HAIRLINE]);
  assert.deepEqual(edgeWeights(LINE_B), [4, 30, 15]);
});

test("no buffer is a hairline, not nothing", () => {
  // Two stations touching is the most important thing on the diagram, and a gap
  // of zero pixels reads as one station.
  assert.equal(edgeWeights(LINE_A)[2], HAIRLINE);
  assert.ok(HAIRLINE > 0);
});

test("the widest gap is the unit, and the rest are fractions of it", () => {
  assert.deepEqual(edgeFractions(LINE_A), [1, 8 / 20, HAIRLINE / 20]);
  assert.deepEqual(edgeFractions(LINE_B), [4 / 30, 1, 15 / 30]);
});

test("two different buffer maps do not draw the same", () => {
  assert.notDeepEqual(edgeFractions(LINE_A), edgeFractions(LINE_B));
});

test("a line with no buffers anywhere still draws rather than dividing by zero", () => {
  const flat = [{ buffer_units: 0 }, { buffer_units: 0 }, { buffer_units: 0 }];
  assert.deepEqual(edgeFractions(flat), [1, 1]);
});
