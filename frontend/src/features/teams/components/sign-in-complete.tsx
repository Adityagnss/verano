/** Finishes a provider sign-in: trades the refresh cookie for a session, then opens the projects. */
"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"

import { refreshSession } from "@/lib/auth/session"

export function SignInComplete() {
  const router = useRouter()
  useEffect(() => {
    void refreshSession().then((ok) =>
      router.replace(ok ? "/projects" : "/login?error=Sign-in+could+not+be+completed.+Try+again."),
    )
  }, [router])
  return <div className="text-muted-foreground p-8 text-sm">Signing you in...</div>
}
