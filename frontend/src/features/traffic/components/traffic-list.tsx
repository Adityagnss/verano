/** The traffic list with filters, a detail panel, and the "make cases" flow. Not a trace viewer. */
"use client"

import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { TRAFFIC_COPY as C } from "../copy"
import { percent } from "../domain"
import { activeFilters, useMakeCases, useTrace, useTraces } from "../hooks"
import type { TraceFilters } from "../types"
import { ImportDialog } from "./import-dialog"

const NONE: TraceFilters = {
  failed: false,
  low_rated: false,
  long: false,
  new_topic: false,
  unused: false,
  q: "",
}
const FLAGS = ["failed", "low_rated", "long", "new_topic", "unused"] as const

function MakeCases({
  projectId,
  filters,
  selected,
}: {
  projectId: string
  filters: TraceFilters
  selected: string[]
}) {
  const make = useMakeCases(projectId)
  const [variable, setVariable] = useState("input")
  const [max, setMax] = useState(100)
  const send = (dry: boolean) =>
    make.mutate({
      ...(selected.length ? { trace_ids: selected } : { filter: activeFilters(filters) }),
      variable: variable.trim() || "input",
      max_cases: max,
      dry_run: dry,
    })
  return (
    <Section title={C.makeTitle} description={C.makeDescription}>
      <p className="text-sm">{selected.length ? C.makeSelected(selected.length) : C.makeFiltered}</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="make-variable">{C.makeVariable}</Label>
          <Input id="make-variable" value={variable} onChange={(e) => setVariable(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="make-max">{C.makeMax}</Label>
          <Input
            id="make-max"
            type="number"
            min={1}
            max={300}
            value={max}
            onChange={(e) => setMax(Number(e.target.value) || 1)}
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" disabled={make.isPending} onClick={() => send(true)}>
          {C.makePreview}
        </Button>
        <Button disabled={make.isPending} onClick={() => send(false)}>
          {C.makeCreate}
        </Button>
      </div>
      <ErrorMessage error={make.error} />
      {make.data ? (
        <p className="text-sm" role="status">
          {make.data.message}
        </p>
      ) : null}
    </Section>
  )
}

function Detail({ projectId, traceId }: { projectId: string; traceId: string }) {
  const trace = useTrace(projectId, traceId)
  if (!trace.data) return <ErrorMessage error={trace.error} />
  const t = trace.data
  return (
    <div className="bg-subtle flex flex-col gap-3 rounded-lg p-4 text-sm">
      <div>
        <p className="text-text-muted text-xs font-semibold uppercase">
          Question{t.input_truncated ? " (cut)" : ""}
        </p>
        <p className="whitespace-pre-wrap">{t.input_text}</p>
      </div>
      <div>
        <p className="text-text-muted text-xs font-semibold uppercase">
          Answer{t.output_truncated ? " (cut)" : ""}
        </p>
        <p className="whitespace-pre-wrap">{t.output_text || "(no answer)"}</p>
      </div>
      {t.error_message ? <p className="text-danger-strong">{t.error_message}</p> : null}
      {t.scores.length ? (
        <ul className="flex flex-col gap-1">
          {t.scores.map((s) => (
            <li key={s.evaluator_name}>
              {s.evaluator_name}: {percent(s.value)} {s.passed ? "passed" : "failed"}
              {s.judged ? " (judge)" : ""}
              {s.reason ? ` — ${s.reason}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export function TrafficList({ projectId }: { projectId: string }) {
  const [filters, setFilters] = useState<TraceFilters>(NONE)
  const [selected, setSelected] = useState<string[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const list = useTraces(projectId, filters)
  const rows = list.data?.pages.flatMap((p) => p.items) ?? []
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  return (
    <div className="flex flex-col gap-6">
      <Section title={C.title} description={C.subtitle} action={<ImportDialog projectId={projectId} />}>
        <div className="flex flex-wrap items-center gap-2">
          {FLAGS.map((flag) => (
            <Button
              key={flag}
              size="sm"
              className="min-h-10 sm:min-h-0"
              variant={filters[flag] ? "default" : "outline"}
              aria-pressed={filters[flag]}
              onClick={() => setFilters((f) => ({ ...f, [flag]: !f[flag] }))}
            >
              {C.filters[flag]}
            </Button>
          ))}
          <Input
            className="min-h-10 sm:max-w-xs"
            aria-label={C.filters.search}
            placeholder={C.filters.search}
            value={filters.q}
            onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
          />
        </div>
        <ErrorMessage error={list.error} />
        {rows.length === 0 && !list.isLoading ? (
          <div className="flex flex-col gap-4">
            <EmptyState title={C.empty} description={C.emptyHint} />
            <div className="border-border flex flex-col gap-1 rounded-lg border border-dashed p-3 text-sm">
              <StatusBadge>Example, not real traffic</StatusBadge>
              <span className="font-medium">Where is my order? It was due on Monday.</span>
              <span className="text-text-secondary">
                Your order shipped on Monday and should arrive tomorrow.
              </span>
              <span className="flex flex-wrap gap-1.5">
                <StatusBadge tone="success">passed</StatusBadge>
                <StatusBadge tone="violet">1 hidden</StatusBadge>
              </span>
            </div>
          </div>
        ) : (
          <ul className="divide-border flex flex-col divide-y">
            {rows.map((t) => (
              <li key={t.id} className="flex flex-col gap-2 py-3">
                <div className="flex flex-wrap items-start gap-3">
                  <input
                    type="checkbox"
                    aria-label="Select this trace"
                    checked={selected.includes(t.id)}
                    onChange={() => toggle(t.id)}
                    className="mt-1 size-5 sm:size-4"
                  />
                  <button
                    type="button"
                    className="min-h-10 min-w-0 flex-1 text-left"
                    onClick={() => setOpen(open === t.id ? null : t.id)}
                  >
                    <span className="block text-sm font-medium">{t.input_preview || "(empty question)"}</span>
                    <span className="text-text-secondary block text-sm">{t.output_preview}</span>
                  </button>
                  <div className="flex flex-wrap justify-end gap-1.5">
                    <StatusBadge>{t.source}</StatusBadge>
                    {t.status === "error" ? <StatusBadge tone="danger">failed</StatusBadge> : null}
                    {t.passed === true ? <StatusBadge tone="success">passed</StatusBadge> : null}
                    {t.passed === false ? <StatusBadge tone="warning">below the bar</StatusBadge> : null}
                    {t.case_made ? <StatusBadge tone="info">case made</StatusBadge> : null}
                    {t.scrubbed_count ? (
                      <StatusBadge tone="violet">{t.scrubbed_count} hidden</StatusBadge>
                    ) : null}
                  </div>
                </div>
                {open === t.id ? <Detail projectId={projectId} traceId={t.id} /> : null}
              </li>
            ))}
          </ul>
        )}
        {list.hasNextPage ? (
          <Button variant="outline" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}>
            Show more
          </Button>
        ) : null}
      </Section>
      {rows.length ? <MakeCases projectId={projectId} filters={filters} selected={selected} /> : null}
    </div>
  )
}
