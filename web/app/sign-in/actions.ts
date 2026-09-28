"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { SignInState } from "@/app/sign-in/state";
import { SESSION_COOKIE, callApi } from "@/lib/api";

/**
 * What the API returned in its `Set-Cookie`, or null if it set no session.
 *
 * The lifetime is read back out of the header rather than repeated here, so
 * `SESSION_LIFETIME` stays one number in one place (ADR-036) instead of two
 * that drift apart the first time somebody changes it.
 */
function sessionFrom(response: Response): { value: string; maxAge: number } | null {
  for (const header of response.headers.getSetCookie()) {
    const [pair = "", ...attributes] = header.split(";");
    const separator = pair.indexOf("=");
    if (separator < 0 || pair.slice(0, separator).trim() !== SESSION_COOKIE) {
      continue;
    }
    const maxAge = attributes
      .map((attribute) => attribute.trim().split("="))
      .find((parts) => parts[0]?.toLowerCase() === "max-age");
    return {
      value: pair.slice(separator + 1),
      maxAge: Number(maxAge?.[1] ?? 0),
    };
  }
  return null;
}

export async function signIn(_previous: SignInState, form: FormData): Promise<SignInState> {
  const user = String(form.get("user") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (user === "" || password === "") {
    return { error: "กรอกชื่อผู้ใช้และรหัสผ่านให้ครบ" };
  }

  const response = await callApi("/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ user, password }),
  });

  if (response.status === 401) {
    // The API answers every kind of failure with one message on purpose, and
    // this form must not be more helpful than it is: telling somebody the user
    // exists but the password is wrong turns the sign-in screen into a way of
    // listing who works here (src/pdm/api/sessions.py).
    return { error: "ข้อมูลไม่ตรงกับบัญชีใด" };
  }
  if (!response.ok) {
    return { error: `ระบบตอบกลับผิดปกติ (${response.status}) ลองใหม่อีกครั้ง` };
  }

  const session = sessionFrom(response);
  if (session === null) {
    return { error: "ระบบไม่ได้ส่ง session กลับมา แจ้งผู้ดูแลระบบ" };
  }

  // Re-set on this origin with the attributes the API chose. `secure` is on
  // once the install serves over TLS and says so with PDM_COOKIE_SECURE=1
  // (ADR-101); over plain HTTP a secure cookie would never be sent.
  (await cookies()).set({
    name: SESSION_COOKIE,
    value: session.value,
    httpOnly: true,
    secure: process.env.PDM_COOKIE_SECURE === "1",
    sameSite: "strict",
    path: "/",
    maxAge: session.maxAge,
  });

  redirect("/");
}
