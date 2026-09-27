import { redirect } from "next/navigation";

import { homeFor } from "@/lib/screens";
import { requireAccount } from "@/lib/session";

/** No menu to choose from: each role opens straight onto its own work (ADR-093). */
export default async function HomePage() {
  const account = await requireAccount();
  redirect(homeFor(account.role));
}
