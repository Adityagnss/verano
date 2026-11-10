/**
 * Workspace settings: people and invites, shared keys, spending limit and the audit log. What a person sees
 * follows their role (viewers see people and the limit; the audit log is for owners and admins).
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { NativeSelect } from "@/components/ui/select"
import { useSession } from "@/lib/auth/use-session"

import { atLeast, ROLE_TEXT } from "../domain"
import { useMe } from "../hooks"
import { AuditPanel } from "./audit-panel"
import { KeysPanel } from "./keys-panel"
import { LimitPanel } from "./limit-panel"
import { MembersPanel } from "./members-panel"

type Tab = "People" | "Keys" | "Spending limit" | "Audit log"

export function WorkspacePage() {
  const me = useMe()
  const { user } = useSession()
  const [chosen, setChosen] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("People")
  const organizations = me.data?.organizations ?? []
  const current =
    organizations.find((o) => o.id === chosen) ??
    organizations.find((o) => !o.is_personal) ??
    organizations[0]
  const tabs: Tab[] = [
    "People",
    ...(atLeast(current?.role, "member") ? (["Keys"] as Tab[]) : []),
    "Spending limit",
  ]
  if (atLeast(current?.role, "admin")) tabs.push("Audit log")
  const active = tabs.includes(tab) ? tab : "People"

  return (
    <div className="mx-auto flex w-full max-w-[72rem] flex-col gap-6 px-4 py-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">Workspace</h1>
          <p className="text-text-secondary text-sm">
            {current
              ? `You are ${ROLE_TEXT[current.role].label.toLowerCase()} here. ${ROLE_TEXT[current.role].what}`
              : ""}
          </p>
        </div>
        {organizations.length > 1 ? (
          <NativeSelect
            aria-label="Workspace"
            value={current?.id ?? ""}
            onChange={(e) => setChosen(e.target.value)}
            className="h-9 w-64"
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
      <nav className="border-border flex gap-1 border-b" aria-label="Workspace sections">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            aria-current={t === active ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${t === active ? "border-foreground font-medium" : "text-text-secondary border-transparent"}`}
          >
            {t}
          </button>
        ))}
      </nav>
      {current ? (
        <div key={`${current.id}-${active}`}>
          {active === "People" ? (
            <MembersPanel
              organizationId={current.id}
              role={current.role}
              personal={current.is_personal}
              selfId={user?.id}
            />
          ) : null}
          {active === "Keys" ? <KeysPanel organizationId={current.id} role={current.role} /> : null}
          {active === "Spending limit" ? (
            <LimitPanel organizationId={current.id} role={current.role} />
          ) : null}
          {active === "Audit log" ? <AuditPanel organizationId={current.id} /> : null}
        </div>
      ) : null}
    </div>
  )
}
