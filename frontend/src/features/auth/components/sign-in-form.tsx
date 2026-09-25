/**
 * Sign-in screen. After signing in the user goes back to where they were headed (the
 * `next` query parameter set by RequireSession), or to their projects.
 */
"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import type { FormEvent } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"

import { AUTH_COPY } from "../copy"
import { useAuthConfig, useSignIn } from "../hooks"
import { AuthCard } from "./auth-card"
import { Field } from "./field"

const DEFAULT_DESTINATION = "/projects"

function safeDestination(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : DEFAULT_DESTINATION
}

export function SignInForm() {
  const router = useRouter()
  const next = useSearchParams().get("next")
  const signIn = useSignIn()
  const config = useAuthConfig()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await signIn.mutateAsync({ email: String(form.get("email")), password: String(form.get("password")) })
    router.replace(safeDestination(next))
  }

  return (
    <AuthCard title={AUTH_COPY.signInTitle} subtitle={AUTH_COPY.signInSubtitle}>
      <form onSubmit={(event) => void submit(event).catch(() => undefined)} className="flex flex-col gap-4">
        <Field id="email" label={AUTH_COPY.email} type="email" autoComplete="email" required />
        <Field
          id="password"
          label={AUTH_COPY.password}
          type="password"
          autoComplete="current-password"
          required
        />
        <ErrorMessage error={signIn.error} />
        <Button type="submit" size="lg" disabled={signIn.isPending}>
          {signIn.isPending ? AUTH_COPY.signingIn : AUTH_COPY.signIn}
        </Button>
        {config.data?.signup_open ? (
          <Link
            href="/signup"
            className="text-center text-sm text-[var(--brand-accent-soft)] hover:underline"
          >
            {AUTH_COPY.toSignUp}
          </Link>
        ) : null}
      </form>
    </AuthCard>
  )
}
