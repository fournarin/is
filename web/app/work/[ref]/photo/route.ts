/**
 * The photo kept with a report (ADR-142), reached through this server for the
 * reason the manual is (ADR-058): the browser talks only to this origin, and the
 * API still decides who may see it and logs that they did.
 */
import type { NextRequest } from "next/server";

import { callApi } from "@/lib/api";
import { orUnreachable } from "@/lib/redirect";

export function GET(_request: NextRequest, context: { params: Promise<{ ref: string }> }): Promise<Response> {
  return orUnreachable(async () => {
    const { ref } = await context.params;
    const upstream = await callApi(`/work-orders/${encodeURIComponent(ref)}/photo`);
    const headers = new Headers({ "x-content-type-options": "nosniff", "cache-control": "private, max-age=3600" });
    const type = upstream.headers.get("content-type");
    if (type !== null) headers.set("content-type", type);
    return new Response(upstream.body, { status: upstream.status, headers });
  });
}
