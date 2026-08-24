import assert from "node:assert/strict";
import { test } from "node:test";

import { openOrdersIn } from "./open-orders.ts";

test("the open tickets are read out of the API's 409", () => {
  assert.deepEqual(
    openOrdersIn({ detail: { message: "MC-012 already has work open", open_orders: ["WO-1", "WO-2"] } }),
    ["WO-1", "WO-2"],
  );
});

test("a refusal phrased as a sentence yields no tickets rather than throwing", () => {
  // Every other refusal in this API answers with a string, and the screen has to
  // survive meeting one here - a 409 from somewhere else, or an older API.
  assert.deepEqual(openOrdersIn({ detail: "somebody else has it" }), []);
  assert.deepEqual(openOrdersIn(null), []);
  assert.deepEqual(openOrdersIn("nope"), []);
  assert.deepEqual(openOrdersIn({ detail: { open_orders: "WO-1" } }), []);
});

test("anything in the list that is not a reference is dropped", () => {
  assert.deepEqual(openOrdersIn({ detail: { open_orders: ["WO-1", 7, null] } }), ["WO-1"]);
});
