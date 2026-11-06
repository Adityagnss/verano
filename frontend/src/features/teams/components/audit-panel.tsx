/** Audit log: who did what and when, filtered by action, person and dates, and downloadable as CSV or JSON. */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/select"

import { dateTime } from "../domain"
import { type AuditFilters, downloadAuditLog, useAuditActions, useAuditLog, useMembers } from "../hooks"

function startOfDay(value: string): string | undefined {
  return value ? new Date(`${value}T00:00:00`).toISOString() : undefined
}

function startOfNextDay(value: string): string | undefined {
  if (!value) return undefined
  const day = new Date(`${value}T00:00:00`)
  day.setDate(day.getDate() + 1)
  return day.toISOString()
}

export function AuditPanel({ organizationId }: { organizationId: string }) {
  const [action, setAction] = useState("")
  const [actor, setActor] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [exportError, setExportError] = useState<unknown>(null)
  const filters: AuditFilters = {
    action: action || undefined,
    actor_id: actor || undefined,
    since: startOfDay(from),
    until: startOfNextDay(to),
  }
  const log = useAuditLog(organizationId, filters)
  const actions = useAuditActions(organizationId)
  const members = useMembers(organizationId)
  const events = log.data?.pages.flatMap((p) => p.items) ?? []

  async function download(format: "csv" | "json") {
    setExportError(null)
    try {
      await downloadAuditLog(organizationId, format, filters)
    } catch (error) {
      setExportError(error)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <NativeSelect
          aria-label="What happened"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="h-9 w-52"
        >
          <option value="">Everything</option>
          {(actions.data ?? []).map((a) => (
            <option key={a.action} value={a.action}>
              {a.label}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Who"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          className="h-9 w-48"
        >
          <option value="">Anyone</option>
          {(members.data ?? []).map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.name}
            </option>
          ))}
        </NativeSelect>
        <Input
          type="date"
          aria-label="From"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          className="w-40"
        />
        <Input
          type="date"
          aria-label="To"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          className="w-40"
        />
        <Button variant="outline" onClick={() => void download("csv")}>
          Download CSV
        </Button>
        <Button variant="outline" onClick={() => void download("json")}>
          Download JSON
        </Button>
      </div>
      <ErrorMessage error={log.error ?? exportError} />
      <ul className="border-border divide-border divide-y rounded-xl border">
        {events.map((e) => (
          <li key={e.id} className="flex flex-col gap-0.5 px-4 py-3">
            <span className="text-sm">{e.summary}</span>
            <span className="text-text-secondary text-xs">
              {e.action_label} · {e.actor_name ?? "System"} · {dateTime(e.created_at)}
            </span>
          </li>
        ))}
        {!log.isLoading && events.length === 0 ? (
          <li className="text-text-muted px-4 py-8 text-center text-sm">
            Nothing recorded for these filters.
          </li>
        ) : null}
      </ul>
      {log.hasNextPage ? (
        <Button variant="outline" onClick={() => void log.fetchNextPage()} disabled={log.isFetchingNextPage}>
          Show older entries
        </Button>
      ) : null}
      <p className="text-text-muted text-xs">Entries can only be added, never changed or deleted.</p>
    </div>
  )
}
