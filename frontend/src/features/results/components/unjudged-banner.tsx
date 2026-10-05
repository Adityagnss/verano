/**
 * Shown when some answers could not be judged (the judge failed or is missing): says how many,
 * that they are left out of the numbers and never counted as passed, and offers to score again
 * (a new scoring pass), with the judge cost shown before anything is asked.
 */
"use client"

import { CircleAlert } from "lucide-react"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import type { ExperimentOut, ModelMetricsOut } from "@/lib/api/types"

import { RESULTS_COPY } from "../copy"
import { useRescoreEstimate, useScoreAgain } from "../hooks"
import { JudgePicker, useChosenJudge } from "./judge-picker"

export function UnjudgedBanner({
  projectId,
  experiment,
  models,
}: {
  projectId: string
  experiment: ExperimentOut | undefined
  models: ModelMetricsOut[]
}) {
  const again = useScoreAgain(projectId)
  const [asking, setAsking] = useState(false)
  const [picked, setPicked] = useState("")
  const judge = useChosenJudge(projectId, picked)
  const quote = useRescoreEstimate(projectId, asking && experiment ? experiment.id : null, judge)
  const unscored = models.reduce((sum, m) => sum + m.unscored_cases, 0)
  if (unscored === 0) return null
  const total = models.reduce((sum, m) => sum + m.cases, 0)
  const estimate = quote.data
  return (
    <div className="bg-warning-soft text-warning-strong ring-warning/25 flex flex-col gap-2 rounded-xl p-4 text-sm ring-1">
      <p className="flex items-start gap-2">
        <CircleAlert className="mt-0.5 size-4 shrink-0" />
        {RESULTS_COPY.unjudged(unscored, total)}
      </p>
      {experiment ? (
        asking ? (
          <div className="flex flex-col gap-2">
            <JudgePicker projectId={projectId} id="rescore-judge" picked={picked} onPick={setPicked} />
            <p>{RESULTS_COPY.scoreAgainCost(estimate?.judge_calls ?? null, estimate?.judge_cost ?? null)}</p>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={again.isPending}
                onClick={() =>
                  again.mutate({ experimentId: experiment.id, judge }, { onSuccess: () => setAsking(false) })
                }
              >
                {again.isPending ? RESULTS_COPY.scoring : RESULTS_COPY.scoreAgainConfirm}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>
                {RESULTS_COPY.scoreAgainCancel}
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <Button size="sm" variant="outline" onClick={() => setAsking(true)}>
              {RESULTS_COPY.scoreAgain}
            </Button>
          </div>
        )
      ) : null}
      <ErrorMessage error={again.error} />
    </div>
  )
}
