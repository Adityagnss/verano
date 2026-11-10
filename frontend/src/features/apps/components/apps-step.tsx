/**
 * Test your own app: connected apps as cards (name, address, last check, status) with "Test one case" and
 * "Run on my test cases", and a three-step flow to connect a new one.
 */
"use client"

import { Plug, Trash2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import type { AppTargetOut } from "@/lib/api/types"
import { ALL_PROJECT_PAGES, projectHref } from "@/lib/nav"

import { APPS_COPY } from "../copy"
import { sampleInputs } from "../domain"
import type { CheckReading } from "../domain"
import { useApps, useRemoveApp } from "../hooks"
import { ConnectWizard } from "./connect-wizard"
import { TrialPanel } from "./trial-panel"

interface LastCheck {
  ok: boolean
  at: Date
  ms: number | null
}

function AppCard({
  projectId,
  app,
  last,
  onRemove,
  removing,
}: {
  projectId: string
  app: AppTargetOut
  last: LastCheck | undefined
  onRemove: () => void
  removing: boolean
}) {
  const [open, setOpen] = useState(false)
  const run = ALL_PROJECT_PAGES.find((p) => p.key === "run")
  return (
    <li className="bg-card border-border flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 font-medium break-words">{app.name}</span>
        <StatusBadge tone="neutral">{APPS_COPY.mode(app.mode)}</StatusBadge>
        {last ? (
          <StatusBadge tone={last.ok ? "success" : "danger"}>
            {last.ok ? "Working" : "Needs attention"}
          </StatusBadge>
        ) : (
          <StatusBadge tone="neutral">Not checked yet</StatusBadge>
        )}
      </div>
      <p className="text-text-muted font-mono text-xs break-all">
        {app.method} {app.url}
      </p>
      <p className="text-text-secondary text-xs">
        {last
          ? `Last check: ${last.at.toLocaleTimeString()}${last.ms !== null ? `, ${last.ms} ms` : ""}`
          : "Last check: none in this session"}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          className="min-h-10"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {APPS_COPY.testOne}
        </Button>
        {run ? (
          <Button className="min-h-10" render={<Link href={projectHref(projectId, run)} />}>
            {APPS_COPY.runOn}
          </Button>
        ) : null}
        <Button variant="ghost" className="min-h-10 sm:ml-auto" disabled={removing} onClick={onRemove}>
          <Trash2 />
          {APPS_COPY.remove}
        </Button>
      </div>
      {open ? (
        <div className="border-border border-t pt-3">
          <TrialPanel
            projectId={projectId}
            appId={app.id}
            initialInputs={sampleInputs(app.request_template)}
            answerPath={app.answer_path}
            idPrefix={`card-${app.id}`}
          />
        </div>
      ) : null}
    </li>
  )
}

export function AppsStep({ projectId }: { projectId: string }) {
  const apps = useApps(projectId)
  const remove = useRemoveApp(projectId)
  const [connecting, setConnecting] = useState(false)
  const [checks, setChecks] = useState<Record<string, LastCheck>>({})
  const list = apps.data ?? []
  const record = (id: string, reading: CheckReading, ms: number | null) =>
    setChecks((c) => ({ ...c, [id]: { ok: reading.ok, at: new Date(), ms } }))

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <PageIntro
        storageKey="apps"
        title={APPS_COPY.title}
        what={APPS_COPY.what}
        whenToUse={APPS_COPY.whenToUse}
        youGet={APPS_COPY.youGet}
        primaryAction={
          connecting ? undefined : (
            <Button size="lg" onClick={() => setConnecting(true)}>
              {APPS_COPY.connect}
            </Button>
          )
        }
        learnMore="apps"
        hasContent={list.length > 0}
      />
      {apps.error ? <ErrorMessage error={apps.error} /> : null}
      {connecting ? (
        <section aria-label={APPS_COPY.addTitle} className="bg-card border-border rounded-xl border p-4">
          <ConnectWizard
            projectId={projectId}
            onDone={() => setConnecting(false)}
            onCancel={() => setConnecting(false)}
            onChecked={record}
          />
        </section>
      ) : null}
      {list.length === 0 && !apps.isLoading && !connecting ? (
        <EmptyState
          icon={Plug}
          title={APPS_COPY.empty}
          description={APPS_COPY.emptyHint}
          action={
            <Button size="lg" onClick={() => setConnecting(true)}>
              {APPS_COPY.connect}
            </Button>
          }
        />
      ) : null}
      {list.length > 0 ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {list.map((app) => (
            <AppCard
              key={app.id}
              projectId={projectId}
              app={app}
              last={checks[app.id]}
              removing={remove.isPending}
              onRemove={() => remove.mutate(app.id)}
            />
          ))}
        </ul>
      ) : null}
    </div>
  )
}
