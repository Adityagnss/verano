/** Every earlier Improve run of the project, newest first, each with its best candidate; open one to see it again. */
"use client"

import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"

import { IMPROVE_COPY } from "../copy"
import { useImprovementHistory } from "../hooks"

export function History({
  projectId,
  openId,
  onOpen,
}: {
  projectId: string
  openId: string | null
  onOpen: (id: string) => void
}) {
  const history = useImprovementHistory(projectId)
  const items = history.data ?? []
  if (items.length < 2) return null
  return (
    <Section title={IMPROVE_COPY.historyHeading} description={IMPROVE_COPY.historyHint}>
      <ul className="border-border divide-border divide-y rounded-lg border">
        {items.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
            <span className="text-text-muted w-40 text-xs">{new Date(s.created_at).toLocaleString()}</span>
            <StatusBadge tone={s.stage === "done" ? "success" : s.stage === "failed" ? "danger" : "neutral"}>
              {IMPROVE_COPY.stages[s.stage] ?? s.stage}
            </StatusBadge>
            <span className="text-text-secondary min-w-0 flex-1 truncate">
              {s.best_strategy
                ? `${s.candidate_count} candidates · best: ${s.best_strategy} (${IMPROVE_COPY.outcome[s.best_outcome ?? "pending"]})`
                : IMPROVE_COPY.noCandidates}
            </span>
            <Button variant="outline" size="sm" disabled={openId === s.id} onClick={() => onOpen(s.id)}>
              {openId === s.id ? IMPROVE_COPY.viewing : IMPROVE_COPY.open}
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  )
}
