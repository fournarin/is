# ADR-021: Downtime cost is computed per station and buffer, not per line

## Context

The scoring formula treated downtime cost as a constant per line. But the domain
is a **vehicle assembly line**, which has a structural property the food
processing plant the author knows does not: stations are in series, one machine
stopping stops the line - and **not every station is equal**, because the buffers
between them buy different amounts of time.

## Decision

Compute the downtime term at station level:

```
downtime_cost(station) = line production rate
                       x max(0, expected repair time - time the buffer buys)
                       x bottleneck multiplier
```

The simulator must model line topology - station order, buffer sizes,
bottlenecks - rather than only a work queue and a roster.

## Reasons

1. A station with twenty units queued ahead of it buys the technician tens of
   minutes. A bottleneck with no buffer stops the line the instant it stops.
   Weighted equally, the system orders work in a way a technician can see is
   wrong immediately, which destroys ADR-005 directly.
2. **This is the property that defines the domain.** Not modelling it means
   designing a scheduler for a generic factory rather than for the vehicle
   assembly line the advisor described.
3. **It does not wait on plant data.** The topology can be assumed in
   configuration today.
4. It gives the problem more academic substance: buffer-aware priority can be
   reported as a sensitivity result ("as buffers grow, how much does the
   difference between policies shrink"), which is worth more than a single number
   from a single layout and reinforces the first publication direction.

## Consequences

- Configuration needs line topology: station order, buffer sizes, bottleneck
  multipliers.
- Phase 2 scenarios must cover both a well-buffered station and a bottleneck, or
  the change cannot be shown to make a difference.
- A question about the real buffer map goes to the plant, but **it does not
  block**: assumed values carry the work through the whole term, and real numbers
  only change values in a file.
