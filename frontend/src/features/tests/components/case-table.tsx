/**
 * All test cases grouped by category, with a source badge on each (Golden / Your input /
 * Generated) and a filter by source. Each group can approve its drafts in one go after a
 * spot-check, or be regenerated; each case can be edited or deleted.
 */
"use client"

import { CircleCheck, Pencil, RefreshCw, Trash2 } from "lucide-react"
import { useMemo, useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge, type Tone } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ItemOut } from "@/lib/api/types"
import { cn } from "@/lib/utils"

import { TESTS_COPY } from "../copy"
import { useVersionActions } from "../hooks"
import { EditCaseDialog } from "./edit-case-dialog"

const REGENERABLE = new Set(Object.keys(TESTS_COPY.categories))
const SOURCES = ["golden", "input_file", "generated", "traffic"] as const
const SOURCE_TONE: Record<string, Tone> = {
  golden: "gold",
  input_file: "info",
  generated: "violet",
  traffic: "neutral",
}

function inputText(item: ItemOut): string {
  const values = Object.values(item.inputs)
  return values.length === 1 ? String(values[0]) : JSON.stringify(item.inputs)
}

function Answer({ item }: { item: ItemOut }) {
  if (item.expected_output) return <span className="font-mono text-xs">{item.expected_output}</span>
  if (item.rubric?.length)
    return (
      <ul className="list-disc pl-4 text-xs">
        {item.rubric.map((criterion, index) => (
          <li key={index}>{String(criterion)}</li>
        ))}
      </ul>
    )
  return <span className="text-warning-strong text-xs">{TESTS_COPY.noAnswer}</span>
}

type Props = { projectId: string; versionId: string; items: ItemOut[]; frozen: boolean }

export function CaseTable({ projectId, versionId, items, frozen }: Props) {
  const actions = useVersionActions(projectId, versionId)
  const [source, setSource] = useState<string | null>(null)
  const [editing, setEditing] = useState<ItemOut | null>(null)
  const groups = useMemo(() => {
    const byCategory = new Map<string, ItemOut[]>()
    for (const item of items.filter((i) => source === null || i.source === source)) {
      byCategory.set(item.category, [...(byCategory.get(item.category) ?? []), item])
    }
    return [...byCategory.entries()]
  }, [items, source])

  if (items.length === 0) return <EmptyState title={TESTS_COPY.tableHeading} description={TESTS_COPY.empty} />
  const error =
    actions.approveDrafts.error ??
    actions.deleteItem.error ??
    actions.regenerate.error ??
    actions.editItem.error
  return (
    <div className="flex flex-col gap-4">
      <div
        className="bg-subtle ring-border inline-flex self-start rounded-lg p-1 ring-1"
        role="group"
        aria-label="Filter by source"
      >
        {[null, ...SOURCES].map((value) => (
          <button
            key={value ?? "all"}
            type="button"
            aria-pressed={source === value}
            onClick={() => setSource(value)}
            className={cn(
              "rounded-md px-3 py-1 text-sm transition-colors",
              source === value
                ? "bg-card text-foreground ring-border font-medium ring-1"
                : "text-text-secondary hover:text-foreground",
            )}
          >
            {value === null ? TESTS_COPY.filterAll : TESTS_COPY.sources[value]}
          </button>
        ))}
      </div>
      <ErrorMessage error={error} />
      {groups.map(([category, rows]) => {
        const drafts = rows.filter((r) => r.review_status === "draft").length
        return (
          <section key={category} className="border-border overflow-hidden rounded-lg border">
            <header className="bg-subtle border-border flex items-center gap-3 border-b px-3 py-2">
              <h4 className="text-sm font-semibold">{TESTS_COPY.categories[category] ?? category}</h4>
              <StatusBadge tone="neutral">{rows.length}</StatusBadge>
              {drafts ? <StatusBadge tone="warning">{TESTS_COPY.draftCount(drafts)}</StatusBadge> : null}
              <div className="ml-auto flex gap-2">
                {!frozen && drafts > 0 ? (
                  <Button size="sm" variant="outline" onClick={() => actions.approveDrafts.mutate(category)}>
                    {TESTS_COPY.approveCategory(drafts)}
                  </Button>
                ) : null}
                {!frozen && REGENERABLE.has(category) ? (
                  <Button size="sm" variant="ghost" onClick={() => actions.regenerate.mutate(category)}>
                    <RefreshCw />
                    {TESTS_COPY.regenerate}
                  </Button>
                ) : null}
              </div>
            </header>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-1/2">Input</TableHead>
                  <TableHead>{TESTS_COPY.expected}</TableHead>
                  <TableHead className="w-56" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="align-top whitespace-normal">
                      <p className="line-clamp-3 font-mono text-xs">{inputText(item)}</p>
                      {item.context.length ? (
                        <p
                          className="text-muted-foreground mt-1 line-clamp-2 text-xs"
                          title={String(item.context[0])}
                        >
                          {TESTS_COPY.context}: {String(item.context[0])}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      <Answer item={item} />
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="flex flex-nowrap items-center justify-end gap-1">
                        <StatusBadge tone={SOURCE_TONE[item.source]}>
                          {TESTS_COPY.sources[item.source]}
                        </StatusBadge>
                        {item.review_status === "draft" ? (
                          <StatusBadge tone="warning">{TESTS_COPY.draft}</StatusBadge>
                        ) : (
                          <CircleCheck
                            className="text-success size-4"
                            aria-label={TESTS_COPY.approvedBadge}
                          />
                        )}
                        {frozen ? null : (
                          <>
                            <Button
                              size="icon-xs"
                              variant="ghost"
                              aria-label={TESTS_COPY.edit}
                              onClick={() => setEditing(item)}
                            >
                              <Pencil />
                            </Button>
                            <Button
                              size="icon-xs"
                              variant="ghost"
                              aria-label={TESTS_COPY.delete}
                              onClick={() => actions.deleteItem.mutate(item.id)}
                            >
                              <Trash2 />
                            </Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        )
      })}
      <EditCaseDialog item={editing} onClose={() => setEditing(null)} save={actions.editItem} />
    </div>
  )
}
