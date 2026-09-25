/** Everything under /projects needs a signed-in user. */
import type { ReactNode } from "react"

import { RequireSession } from "@/components/common/require-session"

export default function ProjectsLayout({ children }: { children: ReactNode }) {
  return <RequireSession>{children}</RequireSession>
}
