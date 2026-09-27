"use client";

import { useActionState } from "react";

import { signIn } from "@/app/sign-in/actions";
import { NOT_SIGNED_IN } from "@/app/sign-in/state";

export function SignInForm() {
  const [state, action, pending] = useActionState(signIn, NOT_SIGNED_IN);

  return (
    <form action={action}>
      {state.error !== null && (
        <p className="error" role="alert">
          {state.error}
        </p>
      )}

      <label className="field">
        <span>ชื่อผู้ใช้</span>
        <input
          name="user"
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          required
        />
      </label>

      <label className="field">
        <span>รหัสผ่าน</span>
        <input name="password" type="password" autoComplete="current-password" required />
      </label>

      <button type="submit" className="big" disabled={pending}>
        {pending ? "กำลังเข้าสู่ระบบ..." : "เข้าสู่ระบบ"}
      </button>
    </form>
  );
}
