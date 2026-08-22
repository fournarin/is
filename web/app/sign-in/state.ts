/**
 * The form's state, kept out of `actions.ts` on purpose.
 *
 * A `"use server"` file may only export async functions - everything it exports
 * becomes callable over the network - so the initial value cannot live beside
 * the action that returns it. `next build`, eslint and tsc all accept the
 * mistake; only running the page finds it.
 */
export type SignInState = { error: string | null };

export const NOT_SIGNED_IN: SignInState = { error: null };
