# ADR-123: A card shows one crossing time

Written on 2026-10-02, while looking at the shift lead's board after ADR-120 to
ADR-122 were rehearsed. Follows ADR-115, which made a ticket carry the live
forecast.

## Context

One card for MC-001 printed three different crossing times:

- the reason: "คาดว่าจะถึงเกณฑ์ราว 2 ต.ค. 18:34 (คลาดเคลื่อนได้ ± 9 ชม. 7 นาที)"
- why it is ranked first: "คาดว่าจะถึงเกณฑ์ในอีกราว 41 นาที"
- the line overview, for the same fault: "14:03 บวกลบ 18 นาที"

The reason is written once, when the order is issued, and never changed (it is
the record of why the job exists). ADR-115 moves the order's `eta` and
`eta_confidence` with each re-fit, but the sentence kept the issue-time
forecast, which was eight hours wide and four hours late. The owner's question in
the second trial - "รอมาแล้ว 1 ชม. 30 นาที: จริงไหม" - was this kind of
question: a number on the screen that might not be true.

## Decision

1. A prediction's reason no longer carries a time. It says the trend points to
   the threshold; when is a separate field.
2. `TicketView.eta_text` and `Active.eta_text` render the crossing from the
   order's live fields, with its interval, in one sentence (`work.domain.
   when_expected`). Every screen that prints a reason prints it beneath. The
   interval cannot be dropped: the function returns nothing rather than a time
   without one (ADR-020).
3. Orders issued before this keep their old sentence, which still carries the
   issue-time forecast; the live sentence prints beneath it.

## Consequences

- The board, the technician's card, the step screen, the close screen and the
  printed ticket show the same crossing time the line overview does.
- "Why first" still quotes the forecast as it stood when the round proposed the
  job, at most a few minutes earlier; it is the round's reason and stays the
  round's.
