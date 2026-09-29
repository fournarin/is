/**
 * Which answers to a close mean "keep it and send it later".
 *
 * 2026-09-29: with the API stopped, the close route answered 500 and the phone
 * showed "ระบบตอบกลับ 500" and dropped the close. The route now answers 503 for
 * that case, and 503 must be read as the network failure it is.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { reachedNobody } from "./close.ts";

test("the API not answering is kept for later", () => {
  for (const status of [502, 503, 504]) {
    assert.equal(reachedNobody(status), true, String(status));
  }
});

test("a refusal is shown, not queued", () => {
  for (const status of [400, 403, 404, 409, 422, 500]) {
    assert.equal(reachedNobody(status), false, String(status));
  }
});
