/**
 * The answers table, laid out like a spreadsheet: sticky header, one row per model answer,
 * click a header to sort (the server sorts, so it works across every page), choose which
 * columns show, page through the rows, export what the filters select, and click a row to
 * open the answer in full.
 */
"use client"

import { ArrowDown, ArrowUp, ChevronsUpDown, Columns3, Download } from "lucide-react"
import { type ReactNode, useEffect, useRef, useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import type { AnswerRow, LogOptions } from "@/lib/api/types"
import { formatCost, formatMs, versionName } from "@/lib/format"
import { cn } from "@/lib/utils"

import { LOGBOOK_COPY } from "../copy"
import { type AnswerFilters, EMPTY_FILTERS, activeCount } from "../domain"
import { type Paging, downloadLogbookCsv, useAnswers } from "../hooks"
import { AnswerDrawer, type Target } from "./answer-drawer"
import { FilterBar } from "./filter-bar"

type ColumnKey = keyof typeof LOGBOOK_COPY.columns
type Column = {
  key: ColumnKey
  sort?: string
  show: boolean
  cell: (row: AnswerRow) => ReactNode
  className?: string
}

function Rate({ value }: { value: number | null }) {
  if (value === null) return <span className="text-text-muted">—</span>
  return (
    <span className="flex items-center gap-2 tabular-nums">
      <span className="bg-chart-track h-1.5 w-12 overflow-hidden rounded-full" aria-hidden>
        <span
          className="bg-lagoon block h-full rounded-full"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </span>
      {Math.round(value * 100)}%
    </span>
  )
}

function Preview({ text, className }: { text: string | null; className?: string }) {
  if (!text) return <span className="text-text-muted">—</span>
  return (
    <span title={text} className={cn("block max-w-[20rem] truncate font-mono text-xs", className)}>
      {text}
    </span>
  )
}

const SOURCE_LABEL: Record<string, string> = {
  golden: "Golden",
  input_file: "Your file",
  generated: "Generated",
  traffic: "From traffic",
}

const COLUMNS: Column[] = [
  {
    key: "time",
    sort: "time",
    show: true,
    cell: (r) => new Date(r.created_at).toLocaleString(),
    className: "whitespace-nowrap",
  },
  {
    key: "experiment",
    sort: "experiment",
    show: true,
    cell: (r) => <span className="block max-w-[10rem] truncate">{r.experiment}</span>,
  },
  {
    key: "version",
    sort: "version",
    show: true,
    cell: (r) => <StatusBadge tone="brand">{versionName(r.prompt_version)}</StatusBadge>,
  },
  {
    key: "model",
    sort: "model",
    show: true,
    cell: (r) => <span className="font-medium">{r.model}</span>,
    className: "whitespace-nowrap",
  },
  { key: "provider", show: false, cell: (r) => r.provider },
  { key: "run", show: false, cell: (r) => r.run_number },
  { key: "case", sort: "case", show: true, cell: (r) => `#${r.case_number}` },
  {
    key: "source",
    show: true,
    cell: (r) => (
      <StatusBadge tone={r.source === "golden" ? "gold" : "neutral"}>
        {SOURCE_LABEL[r.source] ?? "Generated"}
      </StatusBadge>
    ),
  },
  { key: "category", show: false, cell: (r) => r.category },
  {
    key: "status",
    show: false,
    cell: (r) => <StatusBadge tone={r.status === "succeeded" ? "success" : "danger"}>{r.status}</StatusBadge>,
  },
  {
    key: "passed",
    sort: "passed",
    show: true,
    cell: (r) =>
      r.passed === null ? (
        <span className="text-text-muted">—</span>
      ) : r.passed ? (
        <StatusBadge tone="success">Passed</StatusBadge>
      ) : (
        <StatusBadge tone="danger">Failed</StatusBadge>
      ),
  },
  { key: "quality", sort: "quality", show: true, cell: (r) => <Rate value={r.quality} /> },
  { key: "golden", sort: "golden_match", show: true, cell: (r) => <Rate value={r.golden_match} /> },
  {
    key: "failed",
    show: true,
    cell: (r) =>
      r.failed_checks.length ? (
        <span className="flex flex-wrap gap-1">
          {r.failed_checks.map((c) => (
            <StatusBadge key={c} tone="danger">
              {c.replaceAll("_", " ")}
            </StatusBadge>
          ))}
        </span>
      ) : (
        <span className="text-text-muted">—</span>
      ),
  },
  { key: "input", show: true, cell: (r) => <Preview text={r.input_preview} /> },
  { key: "golden_answer", show: true, cell: (r) => <Preview text={r.golden_answer} /> },
  { key: "output", show: true, cell: (r) => <Preview text={r.output_preview} /> },
  { key: "error", show: false, cell: (r) => <Preview text={r.error} className="text-danger-strong" /> },
  {
    key: "tokens",
    sort: "tokens",
    show: true,
    cell: (r) =>
      r.input_tokens === null
        ? "—"
        : `${r.input_tokens.toLocaleString()} / ${(r.output_tokens ?? 0).toLocaleString()}`,
    className: "whitespace-nowrap tabular-nums",
  },
  {
    key: "cost",
    sort: "cost",
    show: true,
    cell: (r) =>
      r.cost === null ? <span className="text-warning-strong">unknown</span> : formatCost(r.cost),
    className: "tabular-nums",
  },
  {
    key: "latency",
    sort: "latency",
    show: true,
    cell: (r) => (r.latency_ms === null ? "—" : formatMs(r.latency_ms)),
    className: "whitespace-nowrap tabular-nums",
  },
  { key: "temperature", show: false, cell: (r) => r.temperature ?? "—" },
  { key: "max_tokens", show: false, cell: (r) => r.max_tokens ?? "—" },
  { key: "attempts", show: false, cell: (r) => r.attempts },
]
const STORAGE = "verano.logbook.columns"

function visibleColumns(): Set<ColumnKey> {
  const fallback = new Set(COLUMNS.filter((c) => c.show).map((c) => c.key))
  try {
    const saved = window.localStorage.getItem(STORAGE)
    return saved ? new Set(JSON.parse(saved) as ColumnKey[]) : fallback
  } catch {
    return fallback
  }
}

function ColumnMenu({
  shown,
  onChange,
}: {
  shown: Set<ColumnKey>
  onChange: (next: Set<ColumnKey>) => void
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => !box.current?.contains(event.target as Node) && setOpen(false)
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [open])
  return (
    <div ref={box} className="relative">
      <Button variant="outline" onClick={() => setOpen(!open)} aria-expanded={open}>
        <Columns3 />
        {LOGBOOK_COPY.columnsMenu}
      </Button>
      {open ? (
        <div className="bg-card ring-border shadow-float absolute right-0 z-30 mt-1 grid max-h-80 w-64 gap-0.5 overflow-y-auto rounded-xl p-1 ring-1">
          {COLUMNS.map((column) => (
            <label
              key={column.key}
              className="hover:bg-subtle flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm"
            >
              <input
                type="checkbox"
                className="accent-lagoon mt-1"
                checked={shown.has(column.key)}
                onChange={() => {
                  const next = new Set(shown)
                  if (next.has(column.key)) next.delete(column.key)
                  else next.add(column.key)
                  onChange(next)
                }}
              />
              <span className="flex flex-col">
                {LOGBOOK_COPY.columns[column.key].label}
                <span className="text-text-muted text-xs">{LOGBOOK_COPY.columns[column.key].hint}</span>
              </span>
            </label>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function AnswersTab({
  projectId,
  options,
  filters,
  onFilters,
  paging,
  onPaging,
}: {
  projectId: string
  options: LogOptions | undefined
  filters: AnswerFilters
  onFilters: (filters: AnswerFilters) => void
  paging: Paging
  onPaging: (paging: Paging) => void
}) {
  const answers = useAnswers(projectId, filters, paging)
  const [shown, setShown] = useState<Set<ColumnKey>>(
    () => new Set(COLUMNS.filter((c) => c.show).map((c) => c.key)),
  )
  const [open, setOpen] = useState<Target | null>(null)
  const [exportError, setExportError] = useState<unknown>(null)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read the saved choice after mount, so server and client render alike
    setShown(visibleColumns())
  }, [])
  const columns = COLUMNS.filter((c) => shown.has(c.key))
  const page = answers.data
  const rows = page?.items ?? []
  const total = page?.total ?? 0
  const filtering = activeCount(filters, EMPTY_FILTERS) > 0

  function sortBy(key: string) {
    const flip = paging.sort === key && paging.order === "desc" ? "asc" : "desc"
    onPaging({ ...paging, sort: key, order: flip, offset: 0 })
  }

  return (
    <div className="flex flex-col gap-4">
      <FilterBar
        options={options}
        filters={filters}
        onChange={(next) => {
          onFilters(next)
          onPaging({ ...paging, offset: 0 })
        }}
        total={page?.total}
      />
      <ErrorMessage error={answers.error ?? exportError} />
      {answers.isPending ? <Skeleton className="h-72 w-full" /> : null}
      {page && total === 0 ? (
        <EmptyState
          title={filtering ? LOGBOOK_COPY.noMatch : "Nothing logged yet"}
          description={filtering ? "Loosen a filter, or clear them all." : LOGBOOK_COPY.noAnswers}
        />
      ) : null}
      {page && total > 0 ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <ColumnMenu
              shown={shown}
              onChange={(next) => {
                setShown(next)
                try {
                  window.localStorage.setItem(STORAGE, JSON.stringify([...next]))
                } catch {
                  /* private mode: the choice is just not remembered */
                }
              }}
            />
            <Button
              variant="outline"
              onClick={() => void downloadLogbookCsv(projectId, filters, paging).catch(setExportError)}
            >
              <Download />
              {LOGBOOK_COPY.export}
            </Button>
          </div>
          <div className="bg-card ring-border max-h-[68vh] overflow-auto rounded-xl ring-1">
            <table className="w-full min-w-max border-separate border-spacing-0 text-left text-sm">
              <thead>
                <tr>
                  {columns.map((column) => {
                    const copy = LOGBOOK_COPY.columns[column.key]
                    const active = column.sort === paging.sort
                    return (
                      <th
                        key={column.key}
                        title={copy.hint}
                        aria-sort={active ? (paging.order === "asc" ? "ascending" : "descending") : undefined}
                        className="bg-subtle border-border text-text-secondary sticky top-0 z-10 border-b px-3 py-2.5 text-xs font-semibold whitespace-nowrap"
                      >
                        {column.sort ? (
                          <button
                            type="button"
                            onClick={() => sortBy(column.sort ?? "time")}
                            className="hover:text-foreground flex items-center gap-1"
                          >
                            {copy.label}
                            {active ? (
                              paging.order === "asc" ? (
                                <ArrowUp className="size-3.5" />
                              ) : (
                                <ArrowDown className="size-3.5" />
                              )
                            ) : (
                              <ChevronsUpDown className="size-3.5 opacity-40" />
                            )}
                          </button>
                        ) : (
                          copy.label
                        )}
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={row.run_id}
                    tabIndex={0}
                    aria-label={LOGBOOK_COPY.openRow}
                    onClick={() => setOpen(row)}
                    onKeyDown={(event) => event.key === "Enter" && setOpen(row)}
                    className={cn(
                      "hover:bg-lagoon-soft/50 focus-visible:bg-lagoon-soft/60 cursor-pointer outline-none",
                      index % 2 === 1 && "bg-subtle/60",
                    )}
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={cn("border-border border-b px-3 py-2 align-middle", column.className)}
                      >
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <label className="text-text-secondary flex items-center gap-2">
              Rows per page
              <NativeSelect
                value={paging.limit}
                onChange={(event) => onPaging({ ...paging, limit: Number(event.target.value), offset: 0 })}
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
              {LOGBOOK_COPY.pageOf(paging.offset + 1, Math.min(paging.offset + paging.limit, total), total)}
            </span>
            <span className="flex gap-2">
              <Button
                variant="outline"
                disabled={paging.offset === 0}
                onClick={() => onPaging({ ...paging, offset: Math.max(0, paging.offset - paging.limit) })}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                disabled={paging.offset + paging.limit >= total}
                onClick={() => onPaging({ ...paging, offset: paging.offset + paging.limit })}
              >
                Next
              </Button>
            </span>
          </div>
        </div>
      ) : null}
      <AnswerDrawer projectId={projectId} target={open} onClose={() => setOpen(null)} onOpen={setOpen} />
    </div>
  )
}
