/**
 * How wide the gap between two stations is drawn.
 *
 * ADR-063 §4: `buffer_units` is what stands between that station and the next,
 * so the edge *after* a station is that station's own buffer. Drawn as equal
 * boxes a reader cannot see why the ranking is what it is - a red station with
 * twenty units in front of it is not a red bottleneck, and equal boxes say the
 * two are the same thing (ADR-021).
 *
 * Pure, and tested with two different buffer maps, because "to scale" is a
 * property of the arithmetic rather than of the CSS.
 */

export type Spaced = { buffer_units: number };

/**
 * One weight per gap, in line order. `n` stations give `n - 1` gaps: the last
 * station's buffer feeds whatever is downstream of the line, which this screen
 * does not draw.
 *
 * A zero buffer is drawn as a hairline rather than as nothing. Two stations
 * touching is the most important thing on the diagram - it is what "no buffer"
 * means, and a gap of literally zero pixels reads as one station.
 */
export const HAIRLINE = 0.25;

export function edgeWeights(stations: readonly Spaced[]): number[] {
  return stations
    .slice(0, -1)
    .map((station) => (station.buffer_units > 0 ? station.buffer_units : HAIRLINE));
}

/**
 * The same weights as fractions of the widest gap, which is what a stylesheet
 * can use directly. The largest becomes 1.
 *
 * Relative rather than absolute: the diagram has to fit a phone held sideways
 * and a projector, and only the ratios carry meaning.
 */
export function edgeFractions(stations: readonly Spaced[]): number[] {
  const weights = edgeWeights(stations);
  const widest = Math.max(...weights, HAIRLINE);
  return weights.map((weight) => weight / widest);
}
