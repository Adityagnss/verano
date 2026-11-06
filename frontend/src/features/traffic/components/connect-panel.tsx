/** Connect an app: ingest tokens for the OTLP receiver, and how much was dropped. */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { TRAFFIC_COPY as C } from "../copy"
import { useCreateToken, useRevokeToken, useStats, useTokens } from "../hooks"

export function ConnectPanel({ projectId }: { projectId: string }) {
  const tokens = useTokens(projectId)
  const create = useCreateToken(projectId)
  const revoke = useRevokeToken(projectId)
  const stats = useStats(projectId)
  const [name, setName] = useState("")
  const origin = typeof window === "undefined" ? "" : window.location.origin
  const made = create.data
  return (
    <div className="flex flex-col gap-6">
      <Section title={C.connect.title} description={C.connect.description}>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate(name.trim(), { onSuccess: () => setName("") })
          }}
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor="token-name" className="text-sm font-medium">
              {C.connect.tokenName}
            </label>
            <Input id="token-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <Button type="submit" disabled={create.isPending}>
            {C.connect.create}
          </Button>
        </form>
        <ErrorMessage error={create.error ?? revoke.error} />
        {made ? (
          <div className="bg-subtle flex flex-col gap-2 rounded-lg p-4 text-sm" role="status">
            <p className="font-medium">{C.connect.shownOnce}</p>
            <code className="break-all">{made.token}</code>
            <p className="text-text-secondary">
              OTEL_EXPORTER_OTLP_TRACES_ENDPOINT={origin}
              {made.endpoint}
              <br />
              OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer {made.token}
              <br />
              OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json
            </p>
          </div>
        ) : null}
        <ul className="divide-border flex flex-col divide-y">
          {(tokens.data ?? []).map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>
                {t.name} <span className="text-text-muted">({t.prefix}…)</span>
                {t.revoked_at
                  ? " — revoked"
                  : t.last_used_at
                    ? ` — last used ${new Date(t.last_used_at).toLocaleString()}`
                    : " — never used"}
              </span>
              {t.revoked_at ? null : (
                <Button size="sm" variant="outline" onClick={() => revoke.mutate(t.id)}>
                  {C.connect.revoke}
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Section>
      {stats.data ? (
        <Section title="Received and dropped">
          <p className="text-sm" role="status">
            {stats.data.dropped_recent
              ? C.connect.dropped(stats.data.dropped_recent)
              : C.connect.nothingDropped}
          </p>
          <table className="text-sm">
            <thead>
              <tr className="text-text-muted text-left">
                <th className="pr-4">Day</th>
                <th className="pr-4">Stored</th>
                <th className="pr-4">Over the rate limit</th>
                <th className="pr-4">Over the size limit</th>
                <th>Requests too large</th>
              </tr>
            </thead>
            <tbody>
              {stats.data.days.map((d) => (
                <tr key={d.day}>
                  <td className="pr-4">{d.day}</td>
                  <td className="pr-4">{d.accepted}</td>
                  <td className="pr-4">{d.dropped_rate}</td>
                  <td className="pr-4">{d.dropped_size}</td>
                  <td>{d.rejected_requests}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}
    </div>
  )
}
