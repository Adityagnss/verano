/**
 * API tokens: make a token for CI or your app, choose what it may do (everything you can, or read-only) and which
 * project it covers, see when each was last used, and revoke it. The token is shown once, when it is made.
 */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { useCreateToken, useRevokeToken, useTokenProjects, useTokens } from "../hooks"

const SELECT =
  "border-input bg-background min-h-10 w-full rounded-md sm:w-auto border px-2 text-sm focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
const DAYS = [30, 90, 365]

export function TokensPage() {
  const tokens = useTokens()
  const projects = useTokenProjects()
  const create = useCreateToken()
  const revoke = useRevokeToken()
  const [name, setName] = useState("")
  const [scope, setScope] = useState<"write" | "read">("read")
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
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 py-2">
      <PageIntro
        storageKey="tokens"
        title="API tokens"
        what="A token lets the command line, your CI and your app use Verano without your password."
        whenToUse="a script or build needs to fetch prompts or look at results"
        youGet="a key you can limit to read-only or one project, and revoke at any time"
        learnMore="tokens"
        hasContent={(tokens.data ?? []).length > 0}
      />

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
        <div className="grid gap-3 sm:flex sm:flex-wrap sm:items-end">
          <label className="flex flex-col gap-1 text-sm">
            Name
            <Input
              className="min-h-10 w-full sm:w-52"
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
              onChange={(e) => setScope(e.target.value as "write" | "read")}
            >
              <option value="read">Read only (look and fetch prompts)</option>
              <option value="write">Everything I can do</option>
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
          <Button size="lg" className="min-h-10" disabled={!name.trim() || create.isPending} onClick={make}>
            Make token
          </Button>
        </div>
      </Section>

      <Section title="Your tokens">
        {tokens.data && tokens.data.length === 0 ? (
          <p className="text-text-secondary text-sm">
            No tokens yet. Make one above; it works for the command line and CI.
          </p>
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
