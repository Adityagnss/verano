/**
 * Opening an invite link: shows what it is for, then lets the person sign in or create an account (with the invited
 * email) and join. Expired or withdrawn links say so and tell the person to ask for a new one.
 */
"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { AuthCard } from "@/features/auth/components/auth-card"
import { refreshSession } from "@/lib/auth/session"
import { useSession } from "@/lib/auth/use-session"

import { ROLE_TEXT } from "../domain"
import { useAcceptInvite, useInvitePreview } from "../hooks"

const WORDS: Record<string, string> = {
  expired: "This invite link has expired. Ask the person who invited you to send a new one.",
  revoked: "This invite was withdrawn. Ask the person who invited you to send a new one.",
  accepted: "This invite was already used.",
}

export function InvitePage({ token }: { token: string }) {
  const router = useRouter()
  const preview = useInvitePreview(token)
  const accept = useAcceptInvite()
  const { status } = useSession()
  useEffect(() => {
    if (status === "unknown") void refreshSession()
  }, [status])

  const data = preview.data
  const next = encodeURIComponent(`/invite/${token}`)
  async function join() {
    await accept.mutateAsync(token)
    router.replace("/workspace")
  }

  return (
    <AuthCard
      title="You're invited"
      subtitle={data ? `Join ${data.organization_name}` : "Checking your invite"}
    >
      <div className="flex flex-col gap-4">
        <ErrorMessage error={preview.error ?? accept.error} />
        {data && data.status !== "open" ? <p className="text-sm">{WORDS[data.status]}</p> : null}
        {data && data.status === "open" ? (
          <>
            <p className="text-sm">
              {data.organization_name} invited <strong>{data.email}</strong> as{" "}
              <strong>{ROLE_TEXT[data.role].label}</strong>. {ROLE_TEXT[data.role].what}
            </p>
            {status === "signed-in" ? (
              <Button
                size="lg"
                disabled={accept.isPending}
                onClick={() => void join().catch(() => undefined)}
              >
                Join {data.organization_name}
              </Button>
            ) : (
              <div className="flex flex-col gap-2">
                <Link href={`/signup?invite=${token}&email=${encodeURIComponent(data.email)}`}>
                  <Button size="lg" className="w-full">
                    Create an account
                  </Button>
                </Link>
                <Link href={`/login?next=${next}`} className="text-center text-sm hover:underline">
                  I already have an account
                </Link>
              </div>
            )}
          </>
        ) : null}
      </div>
    </AuthCard>
  )
}
