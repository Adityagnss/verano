/** Workspace settings needs a signed-in user and sits in the account frame (sidebar and slim header). */
import type { ReactNode } from "react"

import { RequireSession } from "@/components/common/require-session"
import { AccountFrame } from "@/features/projects/components/account-frame"

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <RequireSession>
      <AccountFrame>{children}</AccountFrame>
    </RequireSession>
  )
}
