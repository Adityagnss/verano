/**
 * Step 7, Improve: why cases fail (named clusters), 3 candidate prompts with their diffs
 * and scores on the improving cases, the best one checked on held-back cases, then
 * "Accept as new version" when it is really better. When it isn't, the screen says so.
 */
"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { useExperiments } from "@/features/run/hooks"

import { IMPROVE_COPY } from "../copy"
import { useAccept, useLatestSession, useStartImprove } from "../hooks"
import { CandidateCard, percent } from "./candidate-card"

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
  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">{IMPROVE_COPY.title}</h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm">{IMPROVE_COPY.subtitle}</p>
      </div>
      <ErrorMessage error={experiments.error ?? session.error ?? start.error ?? accept.error} />
      <div className="flex max-w-md flex-col gap-1.5">
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
        {!data ? <p className="text-muted-foreground text-xs">{IMPROVE_COPY.startHint}</p> : null}
      </div>
      {data ? (
        <Alert>
          <AlertDescription>
            <span className="font-medium">{IMPROVE_COPY.stages[data.stage]}</span>
            {data.message ? <p>{data.message}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}
      {data?.clusters.length ? (
        <section className="flex flex-col gap-3">
          <h3 className="text-base font-medium">{IMPROVE_COPY.clustersHeading}</h3>
          <div className="grid gap-3 md:grid-cols-2">
            {data.clusters.map((cluster) => (
              <Card key={cluster.id} size="sm">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    {cluster.name}
                    <Badge variant="secondary">{IMPROVE_COPY.cases(cluster.size)}</Badge>
                    {cluster.rule_tag ? <Badge variant="outline">{cluster.rule_tag}</Badge> : null}
                  </CardTitle>
                  <CardDescription>{cluster.hypothesis}</CardDescription>
                </CardHeader>
                <CardContent className="text-muted-foreground text-xs">
                  {cluster.affected_models.map(String).join(", ")}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      ) : null}
      {data?.candidates.length ? (
        <section className="flex flex-col gap-3">
          <h3 className="text-base font-medium">{IMPROVE_COPY.candidatesHeading}</h3>
          <div className="grid gap-3 lg:grid-cols-3">
            {data.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                baseline={data.baseline_optimize_quality}
              />
            ))}
          </div>
        </section>
      ) : null}
      {confirmed ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle>{IMPROVE_COPY.holdoutHeading}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {IMPROVE_COPY.holdout(
              percent(data?.baseline_holdout_quality),
              percent(confirmed.holdout_quality),
            )}
          </CardContent>
        </Card>
      ) : null}
      <PageActions summary={data && !winner && data.stage === "done" ? IMPROVE_COPY.nothingToAccept : null}>
        {primary}
      </PageActions>
    </div>
  )
}
