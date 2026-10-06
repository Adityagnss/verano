/** The Activity page needs a signed-in user. */
import type { ReactNode } from "react"

import { RequireSession } from "@/components/common/require-session"

export default function ActivityLayout({ children }: { children: ReactNode }) {
  return <RequireSession>{children}</RequireSession>
}
