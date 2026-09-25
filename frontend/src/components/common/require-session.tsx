/**
 * Gate for signed-in screens. On first render it tries to restore the session from the
 * refresh cookie (so a reload keeps the user signed in); if that fails it sends the user
 * to /login and remembers where they were going.
 */
"use client"

import { usePathname, useRouter } from "next/navigation"
import { type ReactNode, useEffect } from "react"

import { refreshSession } from "@/lib/auth/session"
import { useSession } from "@/lib/auth/use-session"

import { COMMON_COPY } from "./copy"

export function RequireSession({ children }: { children: ReactNode }) {
  const { status } = useSession()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (status === "unknown") void refreshSession()
    if (status === "signed-out") router.replace(`/login?next=${encodeURIComponent(pathname)}`)
  }, [status, router, pathname])

  if (status !== "signed-in") {
    return <div className="text-muted-foreground p-8 text-sm">{COMMON_COPY.loading}</div>
  }
  return <>{children}</>
}
