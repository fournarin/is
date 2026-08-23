/**
 * A redirect the client can actually follow.
 *
 * `Response.redirect` demands an absolute URL, and the only absolute URL a
 * route handler has to hand is `request.url` - which is the address this
 * process is *listening* on, not the address the client asked for. Inside a
 * container that is `http://0.0.0.0:3000`, and 0.0.0.0 is a bind address rather
 * than a destination: the technician's phone follows the redirect to nowhere.
 *
 * The first rehearsal of the whole stack is what found this (ADR-067). It
 * cannot be reproduced with `next dev` on a laptop, where the address the
 * server listens on and the address the browser used happen to be the same
 * string - which is why it survived three screens and their checks.
 *
 * A relative `Location` is resolved by the client against the URL it requested,
 * which is right in every case: on a laptop, behind a reverse proxy, and on the
 * plant network where the host is whatever the phone was given. RFC 7231
 * §7.1.2 has permitted it since 2014 and every browser has done it for longer.
 */
export function seeOther(path: string): Response {
  // 303 rather than 302 so the client follows with GET. A repeated POST would
  // be a second close of a job that is already closed.
  return new Response(null, { status: 303, headers: { location: path } });
}
