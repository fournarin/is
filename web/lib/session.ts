/**
 * Who is signed in, according to the API.
 *
 * Every answer here comes from `/sessions/current` rather than from anything
 * this application remembers, which is ADR-036 point 4: a role withdrawn this
 * morning has to stop working on the next request, not at the next sign-in.
 */
import { redirect } from "next/navigation";

import { ApiUnreachable, callApi } from "@/lib/api";

/**
 * The four roles of ADR-024, mirrored here only so that TypeScript can name
 * them. What each may *do* is decided by the endpoint; what each is *shown* is
 * decided here, and ADR-036 point 5 is explicit that hiding a button is a
 * convenience rather than the control.
 */
export type Role = "technician" | "engineer" | "supervisor" | "operator";

/** The API's `Whoami`, field for field (src/pdm/api/sessions.py). */
export type Account = {
  user: string;
  display_name: string;
  role: Role;
};

/** The signed-in account, or null when there is no valid session. */
export async function currentAccount(): Promise<Account | null> {
  const response = await callApi("/sessions/current");
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    // Anything else is the API being unwell rather than the visitor being
    // signed out, and sending somebody to the sign-in form for it would have
    // them typing a password that was never the problem.
    throw new Error(`the API answered ${response.status} for /sessions/current`);
  }
  return (await response.json()) as Account;
}

/** The signed-in account, or a redirect to the sign-in form. */
export async function requireAccount(): Promise<Account> {
  let account: Account | null;
  try {
    account = await currentAccount();
  } catch (error) {
    if (error instanceof ApiUnreachable) {
      // Every signed-in screen asks this first, so this is where "the API is
      // not answering" becomes a page a person can read - rendered on the
      // server, so a phone without JavaScript gets it too (2026-09-29).
      redirect("/unreachable");
    }
    throw error;
  }
  if (account === null) {
    redirect("/sign-in");
  }
  return account;
}

/** What a role is called on screen. Thai on screen, English in code. */
export const ROLE_NAMES: Readonly<Record<Role, string>> = {
  technician: "ช่าง",
  engineer: "วิศวกร",
  supervisor: "หัวหน้ากะ",
  operator: "พนักงานประจำเครื่อง",
};
