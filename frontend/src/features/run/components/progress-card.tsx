/** Live progress of one experiment: per model, calls done out of total, failures and cost so far. */
"use client"

import Link from "next/link"

import { StatusBadge, type Tone } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { ExperimentOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { cn } from "@/lib/utils"

import { RUN_COPY } from "../copy"

const TONE: Record<string, Tone> = {
  running: "info",
  planned: "info",
  evaluating: "info",
  completed: "success",
  cancelled: "warning",
  failed: "danger",
}

type Props = { projectId: string; experiment: ExperimentOut; onCancel: () => void; cancelling: boolean }

export function ProgressCard({ projectId, experiment, onCancel, cancelling }: Props) {
  const running = experiment.status === "running" || experiment.status === "planned"
  const finished = ["completed", "cancelled", "failed"].includes(experiment.status)
  return (
    <Card size="sm" className="shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {experiment.name}
          <StatusBadge tone={TONE[experiment.status] ?? "neutral"}>
            {RUN_COPY.status[experiment.status]}
          </StatusBadge>
        </CardTitle>
        {experiment.stop_reason ? <CardDescription>{experiment.stop_reason}</CardDescription> : null}
        <CardAction>
          {running ? (
            <Button variant="outline" size="sm" onClick={onCancel} disabled={cancelling}>
              {RUN_COPY.cancel}
            </Button>
          ) : finished ? (
            <Link href={`/projects/${projectId}/results?experiment=${experiment.id}`}>
              <Button size="sm">{RUN_COPY.results}</Button>
            </Link>
          ) : null}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {experiment.progress.map((model) => {
          const done = model.succeeded + model.failed + model.skipped
          const share = model.total ? Math.round((done / model.total) * 100) : 0
          return (
            <div key={model.model_profile_id} className="flex flex-col gap-1">
              <div className="flex items-center gap-3 text-sm">
                <span className="font-medium">{model.model}</span>
                <span className="text-muted-foreground">{RUN_COPY.progress(done, model.total)}</span>
                {model.failed ? (
                  <span className="text-destructive">{RUN_COPY.failedCalls(model.failed)}</span>
                ) : null}
                <span className="ml-auto">{formatCost(model.cost)}</span>
              </div>
              <div
                className="bg-chart-track h-2 overflow-hidden rounded-full"
                role="progressbar"
                aria-valuenow={share}
              >
                <div
                  className={cn("h-full rounded-full transition-all", finished ? "bg-success" : "bg-lagoon")}
                  style={{ width: `${share}%` }}
                />
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
