/**
 * Pause, Resume and Retry for one run. A run that paused at its budget cap says why (the card shows the reason) and
 * offers Resume with a higher cap: it carries on exactly where it stopped, with no call repeated.
 */
"use client"

import { Pause, Play, RotateCw } from "lucide-react"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ExperimentOut } from "@/lib/api/types"

import { usePauseRun, useResumeRun, useRetryFailed } from "../controls"

const COPY = {
  pause: "Pause",
  resume: "Resume",
  retry: "Retry failed calls",
  capLabel: "New budget cap ($)",
  capHint: "Higher than what is already spent",
  timeLeft: (seconds: number) =>
    seconds >= 90 ? `about ${Math.round(seconds / 60)} min left` : `about ${seconds} s left`,
}

export function RunControls({ projectId, experiment }: { projectId: string; experiment: ExperimentOut }) {
  const pause = usePauseRun(projectId)
  const resume = useResumeRun(projectId)
  const retry = useRetryFailed(projectId)
  const [cap, setCap] = useState("")
  const failed = experiment.progress.reduce((sum, m) => sum + m.failed, 0)
  const running = experiment.status === "running"
  const paused = experiment.status === "paused"
  if (!running && !paused) return null
  const error = pause.error ?? resume.error ?? retry.error
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {running ? (
          <Button
            variant="outline"
            size="sm"
            disabled={pause.isPending}
            onClick={() => pause.mutate(experiment.id)}
          >
            <Pause /> {COPY.pause}
          </Button>
        ) : null}
        {paused ? (
          <>
            {experiment.budget_cap ? (
              <Input
                aria-label={COPY.capLabel}
                title={COPY.capHint}
                placeholder={COPY.capLabel}
                inputMode="decimal"
                className="h-7 w-32"
                value={cap}
                onChange={(event) => setCap(event.target.value)}
              />
            ) : null}
            <Button
              size="sm"
              disabled={resume.isPending}
              onClick={() => resume.mutate({ experimentId: experiment.id, budgetCap: cap.trim() || null })}
            >
              <Play /> {COPY.resume}
            </Button>
          </>
        ) : null}
        {failed > 0 ? (
          <Button
            variant="outline"
            size="sm"
            disabled={retry.isPending}
            onClick={() => retry.mutate(experiment.id)}
          >
            <RotateCw /> {COPY.retry}
          </Button>
        ) : null}
        {running && experiment.eta_seconds != null ? (
          <span className="text-muted-foreground text-xs">{COPY.timeLeft(experiment.eta_seconds)}</span>
        ) : null}
      </div>
      {error ? <ErrorMessage error={error} /> : null}
    </div>
  )
}
