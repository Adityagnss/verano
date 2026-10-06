/**
 * Every call the app made to a model, whatever it was for: running your test cases, writing
 * test cases, AI judges scoring answers, and Improve. Filter by purpose, status, model,
 * provider, experiment, date or text; click a row for the exact request and response.
 */
"use client"

import { Search, X } from "lucide-react"
import { useEffect, useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { MultiSelect } from "@/components/common/multi-select"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import type { CallRow, LogOptions } from "@/lib/api/types"
import { formatCost, formatMs, versionName } from "@/lib/format"
import { cn } from "@/lib/utils"

import { LOGBOOK_COPY } from "../copy"
import { type CallFilters, EMPTY_CALL_FILTERS, activeCount } from "../domain"
import { useCall, useCalls } from "../hooks"

const PURPOSES = [
  { value: "test_run", label: "Running your test cases" },
  { value: "generation", label: "Writing test cases" },
  { value: "judge", label: "AI judge scoring" },
  { value: "assistant", label: "Improving the prompt" },
]
const PURPOSE_LABEL = Object.fromEntries(PURPOSES.map((p) => [p.value, p.label]))
const HEAD = [
  "Time",
  "Purpose",
  "Step",
  "Model",
  "Experiment",
  "Status",
  "Tokens in / out",
  "Cost",
  "Time taken",
  "Tries",
  "Request",
  "Response",
]

function CallDrawer({
  projectId,
  id,
  onClose,
}: {
  projectId: string
  id: string | null
  onClose: () => void
}) {
  const detail = useCall(projectId, id)
  useEffect(() => {
    if (!id) return
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onClose()
    document.addEventListener("keydown", escape)
    return () => document.removeEventListener("keydown", escape)
  }, [id, onClose])
  if (!id) return null
  const data = detail.data
  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Model call detail">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 bg-[#14203a]/40"
        onClick={onClose}
      />
      <aside className="bg-card absolute inset-y-0 right-0 flex w-[min(54rem,100vw)] flex-col shadow-2xl">
        <header className="border-border flex items-start justify-between gap-3 border-b px-5 py-4">
          <div>
            <p className="text-text-secondary text-xs">
              {data ? new Date(data.row.created_at).toLocaleString() : "Model call"}
            </p>
            <h3 className="mt-0.5 flex flex-wrap items-center gap-2 text-lg font-semibold">
              {data?.row.model ?? "Loading…"}
              {data ? (
                <StatusBadge tone="brand">{PURPOSE_LABEL[data.row.purpose] ?? data.row.purpose}</StatusBadge>
              ) : null}
              {data ? (
                <StatusBadge tone={data.row.status === "succeeded" ? "success" : "danger"}>
                  {data.row.status}
                </StatusBadge>
              ) : null}
            </h3>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X />
          </Button>
        </header>
        <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-5 py-5">
          <ErrorMessage error={detail.error} />
          {detail.isPending ? <Skeleton className="h-64 w-full" /> : null}
          {data ? (
            <>
              <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                {[
                  ["Provider", data.row.provider],
                  ["Tokens in / out", `${data.row.input_tokens ?? "—"} / ${data.row.output_tokens ?? "—"}`],
                  ["Cost", data.row.cost === null ? "unknown price" : formatCost(data.row.cost)],
                  ["Time taken", data.row.latency_ms === null ? "—" : formatMs(data.row.latency_ms)],
                  ["First word after", data.row.ttft_ms === null ? "—" : formatMs(data.row.ttft_ms)],
                  ["Tries", data.row.attempts],
                  ["Finish reason", data.finish_reason ?? "—"],
                  ["Trace id", data.trace_id],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex flex-col">
                    <dt className="text-text-muted text-xs">{label}</dt>
                    <dd className="font-medium break-all tabular-nums">{value}</dd>
                  </div>
                ))}
              </dl>
              {data.row.error ? (
                <p className="bg-danger-soft text-danger-strong rounded-lg p-3 text-sm">{data.row.error}</p>
              ) : null}
              <section className="flex flex-col gap-2">
                <h4 className="text-sm font-semibold">Request</h4>
                {(data.request_messages as { role?: string; content?: string }[]).map((message, index) => (
                  <div key={index} className="flex flex-col gap-1">
                    <p className="text-text-secondary text-xs font-medium capitalize">{message.role}</p>
                    <pre className="bg-subtle ring-border max-h-72 overflow-auto rounded-lg p-3 font-mono text-xs break-words whitespace-pre-wrap ring-1">
                      {message.content}
                    </pre>
                  </div>
                ))}
              </section>
              <section className="flex flex-col gap-2">
                <h4 className="text-sm font-semibold">Response</h4>
                <pre className="bg-subtle ring-border max-h-96 overflow-auto rounded-lg p-3 font-mono text-xs break-words whitespace-pre-wrap ring-1">
                  {data.output_text ?? "—"}
                </pre>
              </section>
              <section className="flex flex-col gap-2">
                <h4 className="text-sm font-semibold">Settings and labels</h4>
                <pre className="bg-subtle ring-border overflow-auto rounded-lg p-3 font-mono text-xs ring-1">
                  {JSON.stringify({ params: data.params, labels: data.labels }, null, 2)}
                </pre>
              </section>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  )
}

export function CallsTab({ projectId, options }: { projectId: string; options: LogOptions | undefined }) {
  const [filters, setFilters] = useState<CallFilters>(EMPTY_CALL_FILTERS)
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState(50)
  const [open, setOpen] = useState<CallRow | null>(null)
  const calls = useCalls(projectId, filters, offset, limit, true)
  const set = <K extends keyof CallFilters>(key: K, value: CallFilters[K]) => {
    setFilters({ ...filters, [key]: value })
    setOffset(0)
  }
  const page = calls.data
  const total = page?.total ?? 0
  const active = activeCount(filters, EMPTY_CALL_FILTERS) > 0
  return (
    <div className="flex flex-col gap-4">
      <div className="bg-card ring-border flex flex-col gap-3 rounded-xl p-3 ring-1">
        <div className="relative">
          <Search className="text-text-muted absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={filters.q}
            onChange={(event) => set("q", event.target.value)}
            placeholder="Search what was sent and what came back"
            aria-label="Search model calls"
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MultiSelect
            label="Purpose"
            value={filters.purposes}
            onChange={(v) => set("purposes", v)}
            choices={PURPOSES}
          />
          <MultiSelect
            label="Status"
            value={filters.statuses}
            onChange={(v) => set("statuses", v)}
            choices={[
              { value: "succeeded", label: "Succeeded" },
              { value: "failed", label: "Failed" },
            ]}
          />
          <MultiSelect
            label="Model"
            value={filters.models}
            onChange={(v) => set("models", v)}
            choices={(options?.models ?? []).map((m) => ({ value: m, label: m }))}
          />
          <MultiSelect
            label="Provider"
            value={filters.providers}
            onChange={(v) => set("providers", v)}
            choices={(options?.providers ?? []).map((m) => ({ value: m, label: m }))}
          />
          <MultiSelect
            label="Experiment"
            value={filters.experiment_ids}
            onChange={(v) => set("experiment_ids", v)}
            choices={(options?.experiments ?? []).map((e) => ({
              value: e.id,
              label: e.name,
              hint: versionName(e.prompt_version),
            }))}
          />
          <label className="text-text-secondary flex items-center gap-1.5 text-sm">
            From
            <Input
              type="date"
              value={filters.date_from}
              onChange={(e) => set("date_from", e.target.value)}
              className="h-9 w-40"
            />
          </label>
          <label className="text-text-secondary flex items-center gap-1.5 text-sm">
            To
            <Input
              type="date"
              value={filters.date_to}
              onChange={(e) => set("date_to", e.target.value)}
              className="h-9 w-40"
            />
          </label>
          {active ? (
            <Button variant="ghost" size="sm" onClick={() => (setFilters(EMPTY_CALL_FILTERS), setOffset(0))}>
              {LOGBOOK_COPY.clear}
            </Button>
          ) : null}
          <span className="text-text-secondary ml-auto text-sm" aria-live="polite">
            {page ? `${total.toLocaleString()} ${total === 1 ? "call" : "calls"}` : ""}
          </span>
        </div>
      </div>
      <ErrorMessage error={calls.error} />
      {calls.isPending ? <Skeleton className="h-72 w-full" /> : null}
      {page && total === 0 ? (
        <EmptyState
          title={active ? "No calls match these filters" : "No model calls yet"}
          description={
            active ? "Loosen a filter, or clear them all." : "Every call to a model will be logged here."
          }
        />
      ) : null}
      {page && total > 0 ? (
        <>
          <div className="bg-card ring-border max-h-[68vh] overflow-auto rounded-xl ring-1">
            <table className="w-full min-w-max border-separate border-spacing-0 text-left text-sm">
              <thead>
                <tr>
                  {HEAD.map((h) => (
                    <th
                      key={h}
                      className="bg-subtle border-border text-text-secondary sticky top-0 z-10 border-b px-3 py-2.5 text-xs font-semibold whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {page.items.map((row, index) => (
                  <tr
                    key={row.id}
                    tabIndex={0}
                    onClick={() => setOpen(row)}
                    onKeyDown={(event) => event.key === "Enter" && setOpen(row)}
                    className={cn(
                      "hover:bg-lagoon-soft/50 focus-visible:bg-lagoon-soft/60 cursor-pointer outline-none",
                      index % 2 === 1 && "bg-subtle/60",
                    )}
                  >
                    <td className="border-border border-b px-3 py-2 whitespace-nowrap">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                    <td className="border-border border-b px-3 py-2 whitespace-nowrap">
                      {PURPOSE_LABEL[row.purpose] ?? row.purpose}
                    </td>
                    <td className="border-border border-b px-3 py-2 font-mono text-xs whitespace-nowrap">
                      {row.step ?? "—"}
                    </td>
                    <td className="border-border border-b px-3 py-2 font-medium whitespace-nowrap">
                      {row.model}
                    </td>
                    <td className="border-border border-b px-3 py-2">
                      <span className="block max-w-[10rem] truncate">{row.experiment ?? "—"}</span>
                    </td>
                    <td className="border-border border-b px-3 py-2">
                      <StatusBadge tone={row.status === "succeeded" ? "success" : "danger"}>
                        {row.status}
                      </StatusBadge>
                    </td>
                    <td className="border-border border-b px-3 py-2 whitespace-nowrap tabular-nums">
                      {row.input_tokens === null
                        ? "—"
                        : `${row.input_tokens.toLocaleString()} / ${(row.output_tokens ?? 0).toLocaleString()}`}
                    </td>
                    <td className="border-border border-b px-3 py-2 tabular-nums">
                      {row.cost === null ? (
                        <span className="text-warning-strong">unknown</span>
                      ) : (
                        formatCost(row.cost)
                      )}
                    </td>
                    <td className="border-border border-b px-3 py-2 whitespace-nowrap tabular-nums">
                      {row.latency_ms === null ? "—" : formatMs(row.latency_ms)}
                    </td>
                    <td className="border-border border-b px-3 py-2 tabular-nums">{row.attempts}</td>
                    <td className="border-border border-b px-3 py-2">
                      <span
                        title={row.request_preview}
                        className="block max-w-[18rem] truncate font-mono text-xs"
                      >
                        {row.request_preview}
                      </span>
                    </td>
                    <td className="border-border border-b px-3 py-2">
                      <span
                        title={row.response_preview ?? row.error ?? ""}
                        className={cn(
                          "block max-w-[18rem] truncate font-mono text-xs",
                          row.error && "text-danger-strong",
                        )}
                      >
                        {row.response_preview ?? row.error ?? "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <label className="text-text-secondary flex items-center gap-2">
              Rows per page
              <NativeSelect
                value={limit}
                onChange={(event) => (setLimit(Number(event.target.value)), setOffset(0))}
                className="w-20"
              >
                {[25, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </NativeSelect>
            </label>
            <span className="text-text-secondary tabular-nums">
              {LOGBOOK_COPY.pageOf(offset + 1, Math.min(offset + limit, total), total)}
            </span>
            <span className="flex gap-2">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                disabled={offset + limit >= total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </span>
          </div>
        </>
      ) : null}
      <CallDrawer projectId={projectId} id={open?.id ?? null} onClose={() => setOpen(null)} />
    </div>
  )
}
