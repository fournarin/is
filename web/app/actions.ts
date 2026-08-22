"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { SESSION_COOKIE, callApi } from "@/lib/api";

export async function signOut(): Promise<void> {
  // Ends the row, not only the cookie. A token whose row outlives the sign-out
  // is a token whoever holds it can still use, and being able to stop somebody
  // *now* is the whole reason a session is a row here (ADR-036).
  await callApi("/sessions", { method: "DELETE" });
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/sign-in");
}
