/**
 * Step 7, Improve: why cases fail (named clusters), 3 candidate prompts with their diffs
 * and scores on the improving cases, the best one checked on held-back cases, then
 * "Accept as new version" when it is really better. When it isn't, the screen says so.
 */
"use client"

import { CircleCheck, Info } from "lucide-react"
import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { ComparisonDetail } from "@/features/results/components/comparison-detail"
import { PageActions } from "@/components/common/page-actions"
import { DatasetWarnings } from "@/components/common/dataset-warnings"
import { Section } from "@/components/common/section"
import { StatTile } from "@/components/common/stat-tile"
import { StatusBadge } from "@/components/common/status-badge"
import { PageIntro } from "@/components/common/page-intro"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { JudgePicker, useChosenJudge } from "@/features/results/components/judge-picker"
import { useExperiments } from "@/features/run/hooks"
import { ALL_PROJECT_PAGES } from "@/lib/nav"
import { cn } from "@/lib/utils"

import { IMPROVE_COPY } from "../copy"
import {
  useAccept,
  useContinueImprove,
  useImprovement,
  useLatestSession,
  useSaveCandidate,
  useStartImprove,
  useStopImprove,
} from "../hooks"
import { formatCost } from "@/lib/format"

import { History } from "./history"
import { CandidateCard, percent } from "./candidate-card"
import { ResultDialog } from "./result-dialog"
import { SessionTree } from "./session-tree"
import { StageTracker } from "./stage-tracker"
import { VerdictCard } from "./verdict-card"

const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "improve")!

/** Improve tests 3 candidates on the 70% it improves on and re-checks the best on the 30% held back: about 2.4 runs. */
const COST_FACTOR = 2.4

export function ImproveStep({ projectId, experimentId }: { projectId: string; experimentId: string | null }) {
  const router = useRouter()
  const experiments = useExperiments(projectId)
  const finished = (experiments.data ?? []).filter((e) => e.origin === "manual" && e.status === "completed")
  const chosen = experimentId ?? finished[0]?.id ?? null
  const chosenCost = Number(
    (finished.find((e) => e.id === chosen)?.progress ?? []).reduce((sum, m) => sum + Number(m.cost), 0),
  )
  const latest = useLatestSession(projectId, chosen)
  const [viewId, setViewId] = useState<string | null>(null)
  const opened = useImprovement(projectId, viewId)
  const session = viewId ? opened : latest
  const start = useStartImprove(projectId)
  const accept = useAccept(projectId)
  const stop = useStopImprove(projectId)
  const save = useSaveCandidate(projectId)
  const resume = useContinueImprove(projectId)
  const data = session.data ?? null
  const winner = data?.candidates.find((c) => c.outcome === "better") ?? null
  const confirmed = data?.candidates.find((c) => c.holdout_experiment_id) ?? null
  const stopped = data?.stage === "failed" || data?.stage === "stopped"
  const running =
    data?.stage === "analyzing" ||
    data?.stage === "quick" ||
    data?.stage === "testing" ||
    data?.stage === "confirming"
  const [writerKey, setWriterKey] = useState("")
  const writer = useChosenJudge(projectId, writerKey)
  const [decided, setDecided] = useState<string[]>(() => {
    try {
      return JSON.parse(window.localStorage.getItem("verano.improve.decided") ?? "[]") as string[]
    } catch {
      return []
    }
  })
  const decide = (id: string) => {
    setDecided((now) => {
      const next = [...now, id].slice(-50)
      try {
        window.localStorage.setItem("verano.improve.decided", JSON.stringify(next))
      } catch {
        /* private mode: the pop-up may show again */
      }
      return next
    })
  }

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
    const done = await accept.mutateAsync({ sessionId: data.id, candidateId: winner.id })
    toast.success(IMPROVE_COPY.accepted)
    if (done.started_experiment_id)
      router.push(`/projects/${projectId}/results?experiment=${done.started_experiment_id}`)
  }

  // The first try uses the experiment's judge unless another model is picked; a retry uses the pick
  // (or the suggested model), since the judge is often why it stopped.
  const primary = !data ? (
    <Button
      size="lg"
      disabled={!chosen || start.isPending}
      onClick={() => chosen && start.mutate({ experimentId: chosen, writer: writerKey ? writer : null })}
    >
      {IMPROVE_COPY.start}
    </Button>
  ) : stopped ? (
    <Button
      size="lg"
      disabled={!chosen || !writer || start.isPending}
      onClick={() => chosen && start.mutate({ experimentId: chosen, writer })}
    >
      {IMPROVE_COPY.retry}
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
  const popUp =
    data?.stage === "done" && winner !== null && winner.outcome === "better" && !decided.includes(winner.id)
  const better = data?.stage === "done" && winner !== null
  const delta =
    confirmed?.holdout_quality !== null &&
    confirmed?.holdout_quality !== undefined &&
    data?.baseline_holdout_quality !== null
      ? (confirmed.holdout_quality ?? 0) - (data?.baseline_holdout_quality ?? 0)
      : null
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <PageIntro
        storageKey="improve"
        title={PAGE.label}
        what={IMPROVE_COPY.what}
        whenToUse={IMPROVE_COPY.whenToUse}
        youGet={IMPROVE_COPY.youGet}
        learnMore="improve"
        hasContent={Boolean(data)}
      />
      <Section title={IMPROVE_COPY.settingsHeading} description={IMPROVE_COPY.subtitle}>
        <div className="flex w-full flex-col gap-1.5 sm:max-w-md">
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
        {!data || stopped ? (
          <details>
            <summary className="text-accent min-h-10 cursor-pointer py-2 text-sm">
              {IMPROVE_COPY.advanced}
            </summary>
            <div className="flex w-full flex-col gap-1 pt-2 sm:max-w-md">
              <JudgePicker
                projectId={projectId}
                id="writer"
                picked={writerKey}
                onPick={setWriterKey}
                label={IMPROVE_COPY.writerLabel}
                forJudging={false}
              />
              <p className="text-text-muted text-xs">{IMPROVE_COPY.writerHint(data?.writer_model)}</p>
            </div>
          </details>
        ) : null}
      </Section>
      <ErrorMessage
        error={
          experiments.error ??
          session.error ??
          start.error ??
          accept.error ??
          stop.error ??
          resume.error ??
          save.error
        }
      />
      {!data || stopped ? <DatasetWarnings projectId={projectId} /> : null}
      {viewId ? (
        <div className="bg-subtle ring-border flex items-center justify-between rounded-lg p-3 text-sm ring-1">
          <span>
            {IMPROVE_COPY.viewing}: {data ? new Date(data.created_at).toLocaleString() : ""}
          </span>
          <Button variant="ghost" size="sm" onClick={() => setViewId(null)}>
            ×
          </Button>
        </div>
      ) : null}
      {data ? <StageTracker stage={data.stage} /> : null}
      {data ? <SessionTree projectId={projectId} session={data} /> : null}
      {data && (data.message || running) ? (
        <div
          className={cn(
            "flex flex-wrap items-start gap-3 rounded-xl p-4 text-sm ring-1",
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
          <div className="min-w-0 flex-1">
            <p className="font-semibold">{IMPROVE_COPY.stages[data.stage]}</p>
            {data.message ? <p>{data.message}</p> : null}
            {data.stage === "testing" && data.candidates.length ? (
              <p className="text-text-muted">
                {IMPROVE_COPY.working(
                  data.candidates.filter((c) => c.optimize_quality !== null).length,
                  data.candidates.filter((c) => c.outcome !== "rejected").length,
                )}
              </p>
            ) : null}
          </div>
          {running ? (
            <Button
              variant="outline"
              className="min-h-10"
              disabled={stop.isPending}
              onClick={() => stop.mutate(data.id)}
            >
              {IMPROVE_COPY.stop}
            </Button>
          ) : null}
          {stopped ? (
            <Button className="min-h-10" disabled={resume.isPending} onClick={() => resume.mutate(data.id)}>
              {IMPROVE_COPY.continue}
            </Button>
          ) : null}
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
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                baseline={data.baseline_optimize_quality}
                saving={save.isPending}
                onSave={async (run) => {
                  const done = await save.mutateAsync({ sessionId: data.id, candidateId: candidate.id, run })
                  if (done.started_experiment_id)
                    router.push(`/projects/${projectId}/results?experiment=${done.started_experiment_id}`)
                }}
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
          {confirmed.verdict ? (
            <VerdictCard
              reason={confirmed.verdict.reason}
              before={data?.baseline_holdout_quality}
              after={confirmed.holdout_quality}
            >
              <p className="text-sm font-semibold">
                {IMPROVE_COPY.verdictHeading} {IMPROVE_COPY.reasons[confirmed.verdict.reason]}
              </p>
              {confirmed.verdict.comparison ? (
                <ComparisonDetail comparison={confirmed.verdict.comparison} />
              ) : null}
            </VerdictCard>
          ) : null}
        </Section>
      ) : null}
      {popUp && winner && data ? (
        <ResultDialog
          open
          candidate={winner}
          before={data.baseline_holdout_quality}
          after={winner.holdout_quality}
          busy={save.isPending || accept.isPending}
          onReject={() => {
            decide(winner.id)
            toast(IMPROVE_COPY.result.rejected)
          }}
          onSave={() =>
            void save
              .mutateAsync({ sessionId: data.id, candidateId: winner.id, run: false })
              .then(() => {
                decide(winner.id)
                toast.success(IMPROVE_COPY.saved)
              })
              .catch(() => undefined)
          }
          onSaveAndTest={() =>
            void acceptWinner()
              .then(() => decide(winner.id))
              .catch(() => undefined)
          }
        />
      ) : null}
      <History projectId={projectId} openId={viewId ?? data?.id ?? null} onOpen={setViewId} />
      <PageActions
        summary={
          !data && chosenCost > 0
            ? IMPROVE_COPY.costHint(formatCost(chosenCost * COST_FACTOR))
            : data && !winner && data.stage === "done"
              ? confirmed?.verdict
                ? IMPROVE_COPY.acceptOff
                : IMPROVE_COPY.nothingToAccept
              : null
        }
      >
        {primary}
      </PageActions>
    </div>
  )
}
