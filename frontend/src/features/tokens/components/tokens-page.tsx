/**
 * API tokens: make a token for CI or your app, choose what it may do (everything you can, or read-only) and which
 * project it covers, see when each was last used, and revoke it. The token is shown once, when it is made.
 */
"use client"

import { ArrowLeft } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Logo } from "@/components/common/logo"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { AccountMenu } from "@/features/projects/components/account-menu"

import { useCreateToken, useRevokeToken, useTokenProjects, useTokens } from "../hooks"

const SELECT =
  "border-input bg-background h-9 rounded-md border px-2 text-sm focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
const DAYS = [30, 90, 365]

export function TokensPage() {
  const tokens = useTokens()
  const projects = useTokenProjects()
  const create = useCreateToken()
  const revoke = useRevokeToken()
  const [name, setName] = useState("")
  const [scope, setScope] = useState<"full" | "read">("read")
  const [projectId, setProjectId] = useState("")
  const [days, setDays] = useState(90)
  const [shown, setShown] = useState<string | null>(null)

  async function make() {
    const created = await create.mutateAsync({
      name,
      scope,
      projectId: projectId || null,
      days,
    })
    setShown(created.token)
    setName("")
  }

  return (
    <div className="mx-auto flex w-full max-w-[64rem] flex-col gap-6 px-4 py-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Logo size={32} />
          <Link
            href="/projects"
            className="text-text-secondary hover:text-foreground inline-flex items-center gap-1 text-sm"
          >
            <ArrowLeft className="size-4" aria-hidden /> Projects
          </Link>
        </div>
        <AccountMenu />
      </header>
      <div className="flex flex-col gap-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">API tokens</h1>
        <p className="text-text-secondary text-[0.95rem]">
          A token lets the command line, your CI and your app use Verano without your password. Use a
          read-only token where it only needs to fetch prompts or look at results.
        </p>
      </div>

      <Section title="Make a token" description="You will see the token once. Copy it somewhere safe.">
        <ErrorMessage error={create.error ?? revoke.error ?? tokens.error} />
        {shown ? (
          <div role="status" className="bg-subtle flex flex-col gap-1 rounded-lg px-3 py-2 text-sm">
            <span className="font-medium">Your new token (shown only now):</span>
            <code className="font-mono text-xs break-all">{shown}</code>
            <span className="text-text-secondary">
              In CI, save it as VERANO_API_TOKEN. Close this message once you have copied it.
            </span>
            <Button variant="outline" size="sm" className="self-start" onClick={() => setShown(null)}>
              I have copied it
            </Button>
          </div>
        ) : null}
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <Input
              className="w-52"
              placeholder="for example ci"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            What it may do
            <select
              className={SELECT}
              value={scope}
              onChange={(e) => setScope(e.target.value as "full" | "read")}
            >
              <option value="read">Read only (look and fetch prompts)</option>
              <option value="full">Everything I can do</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Project
            <select className={SELECT} value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">All my projects</option>
              {(projects.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Lasts
            <select className={SELECT} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {DAYS.map((d) => (
                <option key={d} value={d}>
                  {d} days
                </option>
              ))}
            </select>
          </label>
          <Button disabled={!name.trim() || create.isPending} onClick={make}>
            Make token
          </Button>
        </div>
      </Section>

      <Section title="Your tokens">
        {tokens.data && tokens.data.length === 0 ? (
          <p className="text-text-secondary text-sm">No tokens yet.</p>
        ) : null}
        <ul className="flex flex-col gap-2">
          {(tokens.data ?? []).map((t) => (
            <li
              key={t.id}
              className="border-border flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2"
            >
              <span className="font-medium">{t.name}</span>
              <code className="text-text-secondary font-mono text-xs">{t.prefix}…</code>
              <StatusBadge tone={t.scope === "read" ? "info" : "neutral"}>
                {t.scope === "read" ? "read only" : "full access"}
              </StatusBadge>
              <span className="text-text-secondary text-xs">
                {t.revoked_at
                  ? "revoked"
                  : t.expires_at
                    ? `expires ${new Date(t.expires_at).toLocaleDateString()}`
                    : "never expires"}
                {" · "}
                {t.last_used_at ? `last used ${new Date(t.last_used_at).toLocaleDateString()}` : "never used"}
                {t.project_id ? " · one project" : ""}
              </span>
              {t.revoked_at ? null : (
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto"
                  disabled={revoke.isPending}
                  onClick={async () => {
                    await revoke.mutateAsync(t.id)
                    toast.success("Token revoked. It stops working now.")
                  }}
                >
                  Revoke
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}
