/**
 * The one place this application talks to the API, and it only ever runs on the
 * server (ADR-058).
 *
 * The browser never calls the API. It reaches this Next server, which calls the
 * API on its behalf and forwards the session cookie. Two things follow, and
 * both are why the decision was made that way:
 *
 *  - `API_URL` is read per request, so where the API lives is a deployment
 *    setting rather than a string compiled into a JavaScript bundle - which is
 *    what `NEXT_PUBLIC_*` makes it, and which would mean rebuilding the image
 *    for every site it is installed at.
 *  - the session cookie stays `HttpOnly` and same-origin. There is no CORS
 *    configuration anywhere in this system, and nothing running in the browser
 *    can read the token (ADR-036).
 */
import { cookies } from "next/headers";

/** The name the API sets. `SESSION_COOKIE` in src/pdm/api/deps.py. */
export const SESSION_COOKIE = "pdm_session";

function apiBase(): string {
  const url = process.env.API_URL;
  if (url === undefined || url === "") {
    // No default, for the reason ADR-019 gives STORAGE_DIR none: a process that
    // starts against a guessed address looks healthy right up until the first
    // request, and then fails on a machine nobody is watching.
    throw new Error("API_URL is not set - see the web service in docker-compose.yml");
  }
  return url;
}

/**
 * One request to the API, carrying this visitor's session if they have one.
 *
 * Returns the response whatever its status: 401 is an answer this application
 * acts on rather than an error, and the caller is the one that knows which.
 */
export async function callApi(path: string, init: RequestInit = {}): Promise<Response> {
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  const headers = new Headers(init.headers);
  if (session !== undefined) {
    headers.set("cookie", `${SESSION_COOKIE}=${session}`);
  }
  const url = new URL(path, apiBase());
  try {
    return await fetch(url, {
      ...init,
      headers,
      // Nothing this application reads can be cached. A ticket, a queue and a
      // shift's load are all answers about right now.
      cache: "no-store",
    });
  } catch (cause) {
    // Nothing answered: the API is stopped, restarting or unreachable. Named,
    // so the pages that can still be useful - sign-in, the close queue - tell
    // a person that rather than showing an error page (2026-09-29).
    throw new ApiUnreachable(url.pathname, cause);
  }
}

/** The API did not answer at all, as distinct from answering with an error. */
export class ApiUnreachable extends Error {
  constructor(path: string, cause: unknown) {
    super(`the API did not answer for ${path}`, { cause });
    this.name = "ApiUnreachable";
  }
}

/** What a person reads when the API does not answer. */
export const UNREACHABLE = "เชื่อมต่อระบบไม่ได้ชั่วคราว";
