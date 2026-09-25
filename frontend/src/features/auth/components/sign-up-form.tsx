/** Sign-up screen. Creates the account and its personal workspace, then opens projects. */
"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import type { FormEvent } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"

import { AUTH_COPY } from "../copy"
import { useAuthConfig, useSignUp } from "../hooks"
import { AuthCard } from "./auth-card"
import { Field } from "./field"

export function SignUpForm() {
  const router = useRouter()
  const signUp = useSignUp()
  const config = useAuthConfig()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await signUp.mutateAsync({
      name: String(form.get("name")),
      email: String(form.get("email")),
      password: String(form.get("password")),
    })
    router.replace("/projects")
  }

  const closed = config.data?.signup_open === false
  const minLength = config.data?.password_min_length
  return (
    <AuthCard title={AUTH_COPY.signUpTitle} subtitle={AUTH_COPY.signUpSubtitle}>
      <form onSubmit={(event) => void submit(event).catch(() => undefined)} className="flex flex-col gap-4">
        {closed ? <ErrorMessage error={new Error(AUTH_COPY.signupClosed)} /> : null}
        <Field id="name" label={AUTH_COPY.name} autoComplete="name" required />
        <Field id="email" label={AUTH_COPY.email} type="email" autoComplete="email" required />
        <Field
          id="password"
          label={AUTH_COPY.password}
          type="password"
          autoComplete="new-password"
          minLength={minLength}
          hint={minLength ? AUTH_COPY.passwordHint(minLength) : undefined}
          required
        />
        <ErrorMessage error={signUp.error} />
        <Button type="submit" size="lg" disabled={signUp.isPending || closed}>
          {signUp.isPending ? AUTH_COPY.signingUp : AUTH_COPY.signUp}
        </Button>
        <Link href="/login" className="text-center text-sm text-[var(--brand-accent-soft)] hover:underline">
          {AUTH_COPY.toSignIn}
        </Link>
      </form>
    </AuthCard>
  )
}
