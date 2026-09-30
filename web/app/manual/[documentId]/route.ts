/**
 * The manual, reached through this server rather than from the browser.
 *
 * ADR-058 says the browser talks only to this origin, and a page link is where
 * that would otherwise be broken first: an `<a href>` straight at the API is a
 * cross-origin request with no cookie and no CORS. So the bytes come through
 * here, carrying the session, and the API still applies its own RBAC and still
 * writes the access log ADR-019 requires - this route decides nothing.
 *
 * The path is `manual/` and not `manuals/`: the repository's `.gitignore`
 * excludes `manuals/` to keep the plant's NDA documents out of version
 * control, and a source directory that collides with that guard is a source
 * directory that silently does not get committed.
 *
 * `Range` is forwarded and a 206 is passed back untouched, which is what makes
 * "open at page 142" open at page 142: the PDF viewer asks for the bytes it
 * needs. Swallowing the range here would turn every page link into a
 * whole-volume download, and a link that costs forty megabytes is a link
 * nobody taps twice (ADR-019).
 */
import type { NextRequest } from "next/server";

import { callApi } from "@/lib/api";
import { orUnreachable } from "@/lib/redirect";

// Headers that describe the bytes rather than the connection. Anything not
// listed - transfer-encoding, connection - belongs to the hop it arrived on and
// must not be replayed onto this one.
const PASSED_THROUGH = [
  "content-type",
  "content-length",
  "content-range",
  "content-disposition",
  "accept-ranges",
  "etag",
  "last-modified",
];

export function GET(
  request: NextRequest,
  context: { params: Promise<{ documentId: string }> },
): Promise<Response> {
  return orUnreachable(() => handle(request, context));
}

async function handle(
  request: NextRequest,
  context: { params: Promise<{ documentId: string }> },
): Promise<Response> {
  const { documentId } = await context.params;
  const range = request.headers.get("range");

  const upstream = await callApi(`/documents/${encodeURIComponent(documentId)}`, {
    headers: range === null ? {} : { range },
  });

  const headers = new Headers();
  for (const name of PASSED_THROUGH) {
    const value = upstream.headers.get(name);
    if (value !== null) {
      headers.set(name, value);
    }
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
