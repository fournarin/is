/**
 * A close that could not be sent, kept on the device until it can be.
 *
 * The factory network is not reliable, and this is the one place offline
 * behaviour exists. It is deliberately narrow: nothing else is queued, nothing
 * is synced, and no ticket is written locally. A close, though, must never be
 * lost - it is the only record that the job ended, and `actual_minutes`,
 * `blocked_minutes` and the outcome all arrive with it.
 *
 * Everything here is pure over a `StorageLike`, so it can be tested without a
 * browser (`pending-closes.test.ts`, run by `npm test`). The component decides
 * when to call it; this file decides what a queue of closes means.
 */

export type PendingClose = {
  ref: string;
  outcome: string;
  blocked_reason: string[];
  blocked_minutes: number;
  technician_feedback: string | null;
  /** ISO 8601, from the device. Shown so somebody can see how stale it is. */
  queued_at: string;
};

export const STORAGE_KEY = "pdm.pending-closes";

/** The part of `window.localStorage` this uses, so a test can supply its own. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function isPendingClose(value: unknown): value is PendingClose {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const one = value as Record<string, unknown>;
  return (
    typeof one.ref === "string" &&
    one.ref !== "" &&
    typeof one.outcome === "string" &&
    Array.isArray(one.blocked_reason) &&
    typeof one.blocked_minutes === "number" &&
    typeof one.queued_at === "string"
  );
}

/**
 * What is waiting to be sent.
 *
 * Anything unreadable reads as empty rather than throwing. A technician whose
 * phone white-screens because of a half-written string in local storage has
 * lost the queue *and* the screen, which is worse than losing the queue.
 */
export function pending(storage: StorageLike): PendingClose[] {
  const raw = storage.getItem(STORAGE_KEY);
  if (raw === null) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isPendingClose) : [];
  } catch {
    return [];
  }
}

/**
 * Queue one close, replacing any earlier attempt on the same work order.
 *
 * One entry per ref, because two closes of the same job are the same close.
 * Keeping both would send the job's ending twice, and the second would be
 * refused by an API that has already closed it - leaving a queue that can never
 * drain and a screen that says "not sent yet" for ever.
 */
export function enqueue(storage: StorageLike, close: PendingClose): PendingClose[] {
  const kept = pending(storage).filter((one) => one.ref !== close.ref);
  const queue = [...kept, close];
  storage.setItem(STORAGE_KEY, JSON.stringify(queue));
  return queue;
}

/** Drop one, once the API has taken it. */
export function settle(storage: StorageLike, ref: string): PendingClose[] {
  const queue = pending(storage).filter((one) => one.ref !== ref);
  storage.setItem(STORAGE_KEY, JSON.stringify(queue));
  return queue;
}

/**
 * Send everything the device is holding, and say what is still waiting.
 *
 * What is returned is read from the device after sending, not a copy kept from
 * before. Two retries can run at once - the "online" event and a press of
 * "ลองส่งเดี๋ยวนี้" - and the one that finishes last would otherwise report a
 * close the other had already sent as still waiting.
 */
export async function drain(
  storage: StorageLike,
  send: (ref: string, close: PendingClose) => Promise<string>,
): Promise<PendingClose[]> {
  for (const one of pending(storage)) {
    if ((await send(one.ref, one)) === "sent") {
      settle(storage, one.ref);
    }
  }
  return pending(storage);
}
