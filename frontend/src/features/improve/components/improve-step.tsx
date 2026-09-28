/**
 * Step 7, Improve: why cases fail (named clusters), 3 candidate prompts with their diffs
 * and scores on the improving cases, the best one checked on held-back cases, then
 * "Accept as new version" when it is really better. When it isn't, the screen says so.
 */
"use client"

import { CircleCheck, Info } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StatTile } from "@/components/common/stat-tile"
import { StatusBadge } from "@/components/common/status-badge"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { useExperiments } from "@/features/run/hooks"
import { cn } from "@/lib/utils"

import { IMPROVE_COPY } from "../copy"
import { useAccept, useLatestSession, useStartImprove } from "../hooks"
import { CandidateCard, percent } from "./candidate-card"
import { StageTracker } from "./stage-tracker"

export function ImproveStep({ projectId, experimentId }: { projectId: string; experimentId: string | null }) {
  const router = useRouter()
  const experiments = useExperiments(projectId)
  const finished = (experiments.data ?? []).filter((e) => e.origin === "manual" && e.status === "completed")
  const chosen = experimentId ?? finished[0]?.id ?? null
  const session = useLatestSession(projectId, chosen)
  const start = useStartImprove(projectId)
  const accept = useAccept(projectId)
  const data = session.data ?? null
  const winner = data?.candidates.find((c) => c.outcome === "better") ?? null
  const confirmed = data?.candidates.find((c) => c.holdout_experiment_id) ?? null

  if (experiments.data && finished.length === 0)
    return (
      <EmptyState
        title={IMPROVE_COPY.title}
        description={IMPROVE_COPY.none}
        action={
          <Link href={`/projects/${projectId}/run`} className="text-accent text-sm">
            →
          </Link>
        }
      />
    )

  async function acceptWinner() {
    if (!data || !winner) return
    await accept.mutateAsync({ sessionId: data.id, candidateId: winner.id })
    toast.success(IMPROVE_COPY.accepted)
  }

  const primary = !data ? (
    <Button size="lg" disabled={!chosen || start.isPending} onClick={() => chosen && start.mutate(chosen)}>
      {IMPROVE_COPY.start}
    </Button>
  ) : (
    <Button
      size="lg"
      disabled={!winner || accept.isPending}
      onClick={() => void acceptWinner().catch(() => undefined)}
    >
      {IMPROVE_COPY.accept}
    </Button>
  )
  const better = data?.stage === "done" && winner !== null
  const delta =
    confirmed?.holdout_quality !== null &&
    confirmed?.holdout_quality !== undefined &&
    data?.baseline_holdout_quality !== null
      ? (confirmed.holdout_quality ?? 0) - (data?.baseline_holdout_quality ?? 0)
      : null
  return (
    <div className="flex max-w-7xl flex-col gap-6">
      <StepHeader
        step="improve"
        title={IMPROVE_COPY.title}
        description={IMPROVE_COPY.subtitle}
        howItWorks={IMPROVE_COPY.howItWorks}
        aside={
          <div className="flex w-80 flex-col gap-1.5">
            <Label htmlFor="experiment">{IMPROVE_COPY.experiment}</Label>
            <NativeSelect
              id="experiment"
              value={chosen ?? ""}
              onChange={(e) => router.push(`/projects/${projectId}/improve?experiment=${e.target.value}`)}
            >
              {finished.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} · {new Date(e.created_at).toLocaleString()}
                </option>
              ))}
            </NativeSelect>
            {!data ? <p className="text-text-muted text-xs">{IMPROVE_COPY.startHint}</p> : null}
          </div>
        }
      />
      <ErrorMessage error={experiments.error ?? session.error ?? start.error ?? accept.error} />
      {data ? <StageTracker stage={data.stage} /> : null}
      {data?.message ? (
        <div
          className={cn(
            "flex items-start gap-3 rounded-xl p-4 text-sm ring-1",
            better
              ? "bg-success-soft text-success-strong ring-success/25"
              : data.stage === "failed"
                ? "bg-danger-soft text-danger-strong ring-danger/20"
                : "bg-card text-foreground ring-border",
          )}
        >
          {better ? (
            <CircleCheck className="mt-0.5 size-5 shrink-0" />
          ) : (
            <Info className="text-text-muted mt-0.5 size-5 shrink-0" />
          )}
          <div>
            <p className="font-semibold">{IMPROVE_COPY.stages[data.stage]}</p>
            <p>{data.message}</p>
          </div>
        </div>
      ) : null}
      {data?.clusters.length ? (
        <Section number={1} title={IMPROVE_COPY.clustersHeading} description={IMPROVE_COPY.clustersHint}>
          <div className="grid gap-3 md:grid-cols-2">
            {data.clusters.map((cluster) => (
              <div
                key={cluster.id}
                className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-4 ring-1"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{cluster.name}</span>
                  <StatusBadge tone="danger">{IMPROVE_COPY.cases(cluster.size)}</StatusBadge>
                  {cluster.rule_tag ? (
                    <StatusBadge tone="neutral">{cluster.rule_tag.replaceAll("_", " ")}</StatusBadge>
                  ) : null}
                </div>
                <p className="text-text-secondary text-sm">{cluster.hypothesis}</p>
                <p className="text-text-muted text-xs">{cluster.affected_models.map(String).join(", ")}</p>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
      {data?.candidates.length ? (
        <Section number={2} title={IMPROVE_COPY.candidatesHeading} description={IMPROVE_COPY.candidatesHint}>
          <div className="grid gap-3 lg:grid-cols-3">
            {data.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                baseline={data.baseline_optimize_quality}
              />
            ))}
          </div>
        </Section>
      ) : null}
      {confirmed ? (
        <Section number={3} title={IMPROVE_COPY.holdoutHeading} description={IMPROVE_COPY.holdoutHint}>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label={IMPROVE_COPY.currentPrompt} value={percent(data?.baseline_holdout_quality)} />
            <StatTile
              label={IMPROVE_COPY.bestCandidate}
              value={percent(confirmed.holdout_quality)}
              detail={confirmed.strategy}
            />
            <StatTile
              label={IMPROVE_COPY.difference("")}
              value={delta === null ? "—" : `${delta >= 0 ? "+" : ""}${Math.round(delta * 100)}%`}
            />
          </div>
        </Section>
      ) : null}
      <PageActions summary={data && !winner && data.stage === "done" ? IMPROVE_COPY.nothingToAccept : null}>
        {primary}
      </PageActions>
    </div>
  )
}
