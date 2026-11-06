/** "Continue with Google / Microsoft / ..." buttons, shown only for the providers the server has set up. */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import type { SignInProviderOut } from "@/lib/api/types"

import { startProviderSignIn } from "../hooks"

export function SignInProviders({ providers }: { providers: SignInProviderOut[] }) {
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState<string | null>(null)
  if (providers.length === 0) return null

  async function go(name: string) {
    setError(null)
    setBusy(name)
    try {
      window.location.assign(await startProviderSignIn(name))
    } catch (failure) {
      setError(failure)
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {providers.map((p) => (
        <Button
          key={p.name}
          type="button"
          variant="outline"
          size="lg"
          disabled={busy !== null}
          onClick={() => void go(p.name)}
        >
          Continue with {p.display_name}
        </Button>
      ))}
      <ErrorMessage error={error} />
      <p className="text-text-muted text-center text-xs">or use your email</p>
    </div>
  )
}
