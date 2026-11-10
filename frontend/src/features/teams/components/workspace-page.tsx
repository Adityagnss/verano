/**
 * Workspace settings: people and invites, shared keys, spending limit and the audit log. What a person sees
 * follows their role (viewers see people and the limit; the audit log is for owners and admins).
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { NativeSelect } from "@/components/ui/select"
import { useSession } from "@/lib/auth/use-session"

import { atLeast, ROLE_TEXT } from "../domain"
import { useMe } from "../hooks"
import { AuditPanel } from "./audit-panel"
import { KeysPanel } from "./keys-panel"
import { LimitPanel } from "./limit-panel"
import { MembersPanel } from "./members-panel"

type Tab = "Teammates" | "Provider keys" | "Spending limit" | "Activity log"

export function WorkspacePage() {
  const me = useMe()
  const { user } = useSession()
  const [chosen, setChosen] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("Teammates")
  const organizations = me.data?.organizations ?? []
  const current =
    organizations.find((o) => o.id === chosen) ??
    organizations.find((o) => !o.is_personal) ??
    organizations[0]
  const tabs: Tab[] = [
    "Teammates",
    ...(atLeast(current?.role, "member") ? (["Provider keys"] as Tab[]) : []),
    "Spending limit",
  ]
  if (atLeast(current?.role, "admin")) tabs.push("Activity log")
  const active = tabs.includes(tab) ? tab : "Teammates"

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 py-2">
      <PageIntro
        storageKey="workspace"
        title="Workspace"
        what="The people, provider keys and spending limit you share across projects."
        whenToUse="you invite a teammate, share a key or cap monthly spend"
        youGet="one place to manage who can do what"
        learnMore="workspace"
        hasContent
      />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-text-secondary text-sm">
          {current
            ? `You are ${ROLE_TEXT[current.role].label.toLowerCase()} here. ${ROLE_TEXT[current.role].what}`
            : ""}
        </p>
        {organizations.length > 1 ? (
          <NativeSelect
            aria-label="Workspace"
            value={current?.id ?? ""}
            onChange={(e) => setChosen(e.target.value)}
            className="h-9 w-full sm:w-64"
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </NativeSelect>
        ) : null}
      </div>
      <ErrorMessage error={me.error} />
      {user && !user.email_verified ? (
        <p className="bg-muted rounded-lg p-3 text-sm">Your email address isn&apos;t confirmed yet.</p>
      ) : null}
      <Tabs value={active} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList variant="line" aria-label="Workspace sections" className="max-w-full overflow-x-auto">
          {tabs.map((t) => (
            <TabsTrigger key={t} value={t} className="min-h-10 px-3">
              {t}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {current ? (
        <div key={`${current.id}-${active}`}>
          {active === "Teammates" ? (
            <MembersPanel
              organizationId={current.id}
              role={current.role}
              personal={current.is_personal}
              selfId={user?.id}
            />
          ) : null}
          {active === "Provider keys" ? <KeysPanel organizationId={current.id} role={current.role} /> : null}
          {active === "Spending limit" ? (
            <LimitPanel organizationId={current.id} role={current.role} />
          ) : null}
          {active === "Activity log" ? <AuditPanel organizationId={current.id} /> : null}
        </div>
      ) : null}
    </div>
  )
}
