"use client";

import { CircleAlert } from "lucide-react";
import { useActionState } from "react";

import { signIn } from "@/app/sign-in/actions";
import { NOT_SIGNED_IN } from "@/app/sign-in/state";

export function SignInForm() {
  const [state, action, pending] = useActionState(signIn, NOT_SIGNED_IN);

  return (
    <form action={action} className="si-form">
      {state.error !== null && (
        <div className="callout is-bad" role="alert">
          <CircleAlert size={24} aria-hidden />
          <div>{state.error}</div>
        </div>
      )}

      <label className="si-field">
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

      <label className="si-field">
        <span>รหัสผ่าน</span>
        <input name="password" type="password" autoComplete="current-password" required />
      </label>

      <button type="submit" className="btn pri" disabled={pending}>
        {pending ? "กำลังเข้าสู่ระบบ..." : "เข้าสู่ระบบ"}
      </button>
    </form>
  );
}
