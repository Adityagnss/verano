/** Connect an app: ingest tokens for the OTLP receiver, and how much was dropped. */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { CopyButton } from "@/components/common/copy-button"
import { ResponsiveTable } from "@/components/common/responsive-table"
import { Section } from "@/components/common/section"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

import { TRAFFIC_COPY as C } from "../copy"
import { snippets, TESTED_WITH } from "../snippets"
import { useCreateToken, useRevokeToken, useStats, useTokens } from "../hooks"

function Snippets({ endpoint, token }: { endpoint: string; token: string }) {
  const list = snippets(endpoint, token)
  return (
    <Tabs defaultValue="python">
      <TabsList>
        {list.map((s) => (
          <TabsTrigger key={s.id} value={s.id} className="min-h-10 px-3">
            {s.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {list.map((s) => (
        <TabsContent key={s.id} value={s.id} className="flex flex-col gap-2 pt-2">
          <div className="overflow-x-auto">
            <pre className="bg-card rounded-md border p-3 text-xs">{s.code}</pre>
          </div>
          <div>
            <CopyButton text={s.code} label={`Copy ${s.label} setup`} />
          </div>
        </TabsContent>
      ))}
    </Tabs>
  )
}

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
          className="flex flex-col items-stretch gap-3 sm:flex-row sm:flex-wrap sm:items-end"
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
          <Button type="submit" size="lg" disabled={create.isPending}>
            {C.connect.create}
          </Button>
        </form>
        <ErrorMessage error={create.error ?? revoke.error} />
        {made ? (
          <div className="bg-subtle flex flex-col gap-3 rounded-lg p-4 text-sm" role="status">
            <p className="font-medium">{C.connect.shownOnce}</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 break-all">{made.token}</code>
              <CopyButton text={made.token} label="Copy token" />
            </div>
            <Snippets endpoint={`${origin}${made.endpoint}`} token={made.token} />
          </div>
        ) : null}
        <p className="text-text-secondary text-sm">{TESTED_WITH}</p>
        <ul className="divide-border flex flex-col divide-y">
          {(tokens.data ?? []).map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
              <span>
                {t.name} <span className="text-text-muted">({t.prefix}…)</span>
                {t.revoked_at
                  ? " — revoked"
                  : t.last_used_at
                    ? ` — last used ${new Date(t.last_used_at).toLocaleString()}`
                    : " — never used"}
              </span>
              {t.revoked_at ? null : (
                <Button
                  size="sm"
                  variant="outline"
                  className="min-h-10 sm:min-h-0"
                  onClick={() => revoke.mutate(t.id)}
                >
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
          <ResponsiveTable
            caption="Spans received and dropped, by day"
            rows={stats.data.days}
            rowKey={(d) => d.day}
            columns={[
              { id: "day", header: "Day", primary: true, cell: (d) => d.day },
              { id: "stored", header: "Stored", cell: (d) => d.accepted },
              { id: "rate", header: "Over the rate limit", cell: (d) => d.dropped_rate },
              { id: "size", header: "Over the size limit", cell: (d) => d.dropped_size },
              { id: "big", header: "Requests too large", cell: (d) => d.rejected_requests },
            ]}
          />
        </Section>
      ) : null}
    </div>
  )
}
