/** The page an email-confirmation link opens. */
"use client"

import Link from "next/link"
import { useEffect, useRef } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { AuthCard } from "@/features/auth/components/auth-card"

import { useVerifyEmail } from "../hooks"

export function VerifyEmailPage({ token }: { token: string }) {
  const verify = useVerifyEmail()
  const started = useRef(false)
  useEffect(() => {
    if (token && !started.current) {
      started.current = true
      verify.mutate(token)
    }
  }, [token, verify])

  return (
    <AuthCard title="Confirm your email" subtitle="One moment">
      <div className="flex flex-col gap-4 text-sm">
        {!token ? <p>This link is missing its code. Open the link from your email again.</p> : null}
        {verify.isPending ? <p>Checking the link...</p> : null}
        {verify.isSuccess ? <p>Your email address is confirmed. Thank you.</p> : null}
        <ErrorMessage error={verify.error} />
        <Link href="/projects" className="hover:underline">
          Go to your projects
        </Link>
      </div>
    </AuthCard>
  )
}
