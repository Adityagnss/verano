/**
 * Good / bad / not sure buttons for one answer, and what everyone said. A label is stored beside the scores and
 * never changes one; clicking your current label again takes it back.
 */
"use client"

import { Button } from "@/components/ui/button"
import type { LabelSummary } from "@/lib/api/types"
import { cn } from "@/lib/utils"

import { LABEL_COPY } from "../copy"
import { useSetLabel } from "../hooks"

type Verdict = "good" | "bad" | "unsure"
const CHOICES: Verdict[] = ["good", "bad", "unsure"]

export function LabelBar({
  projectId,
  experimentId,
  answerId,
  labels,
}: {
  projectId: string
  experimentId: string
  answerId: string
  labels: LabelSummary | null | undefined
}) {
  const set = useSetLabel(projectId, experimentId)
  const mine = labels?.mine ?? null
  return (
    <div className="mt-2 flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={LABEL_COPY.question}>
        <span className="text-text-muted text-xs">{LABEL_COPY.question}</span>
        {CHOICES.map((verdict) => (
          <Button
            key={verdict}
            type="button"
            size="xs"
            variant={mine === verdict ? "default" : "outline"}
            aria-pressed={mine === verdict}
            disabled={set.isPending}
            className={cn(mine === verdict && "pointer-events-auto")}
            onClick={() => set.mutate({ answerId, verdict: mine === verdict ? null : verdict })}
          >
            {LABEL_COPY[verdict]}
          </Button>
        ))}
      </div>
      {labels ? (
        <p className="text-text-secondary text-xs">
          {LABEL_COPY.majority(labels.verdict, labels.good, labels.bad, labels.unsure)}
        </p>
      ) : null}
      {set.error ? <p className="text-destructive text-xs">{set.error.message}</p> : null}
    </div>
  )
}
