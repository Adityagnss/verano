/** What Verano sent to the app for one answer and what came back, turn by turn (loaded when asked for). */
"use client"

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Skeleton } from "@/components/ui/skeleton"
import { api, call } from "@/lib/api/client"
import type { AppCallOut } from "@/lib/api/types"

import { CALLS_COPY } from "../screens-copy"

function useRecordedCalls(projectId: string, experimentId: string, runId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "app-calls", experimentId, runId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/apps/calls/{experiment_id}/{run_id}", {
          params: { path: { project_id: projectId, experiment_id: experimentId, run_id: runId } },
        }),
      ),
    enabled,
  })
}

/** Request and reply bodies are usually JSON: show them indented when they are, as they came otherwise. */
export function prettyBody(text: string | null): string {
  if (text === null || text === "") return ""
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

function Call({ item }: { item: AppCallOut }) {
  const ok = item.error === null && item.status_code !== null && item.status_code < 400
  return (
    <li className="bg-subtle ring-border flex flex-col gap-2 rounded p-2 ring-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{CALLS_COPY.turn(item.turn)}</span>
        <StatusBadge tone={ok ? "success" : "danger"}>{CALLS_COPY.status(item.status_code)}</StatusBadge>
        <span className="text-text-muted">{CALLS_COPY.latency(item.latency_ms)}</span>
      </div>
      {item.error ? (
        <p className="text-danger-strong" role="alert">
          {CALLS_COPY.failed}: {item.error}
        </p>
      ) : null}
      <div>
        <p className="text-text-muted">{CALLS_COPY.sent}</p>
        <pre className="font-mono whitespace-pre-wrap">{prettyBody(item.request_body)}</pre>
      </div>
      <div>
        <p className="text-text-muted">{CALLS_COPY.received}</p>
        <pre className="font-mono whitespace-pre-wrap">{prettyBody(item.response_body)}</pre>
      </div>
      {item.truncated ? <p className="text-warning-strong">{CALLS_COPY.truncated}</p> : null}
    </li>
  )
}

export function AppCalls({
  projectId,
  experimentId,
  runId,
}: {
  projectId: string
  experimentId: string
  runId: string
}) {
  const [open, setOpen] = useState(false)
  const calls = useRecordedCalls(projectId, experimentId, runId, open)
  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        className="text-accent font-medium hover:underline"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? CALLS_COPY.close : CALLS_COPY.open}
      </button>
      {open ? (
        <div className="mt-1.5 flex flex-col gap-2">
          <p className="font-medium">{CALLS_COPY.heading}</p>
          {calls.isPending ? <Skeleton className="h-16" aria-label={CALLS_COPY.loading} /> : null}
          <ErrorMessage error={calls.error} />
          {calls.data && calls.data.length === 0 ? (
            <p className="text-text-muted">{CALLS_COPY.none}</p>
          ) : null}
          {calls.data?.length ? (
            <ul className="flex flex-col gap-2">
              {calls.data.map((item) => (
                <Call key={item.turn} item={item} />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
