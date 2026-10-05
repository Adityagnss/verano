/**
 * Step 6, Results: pick a finished experiment, then the tradeoff table, one pass-rate
 * chart, and the test cases with every model's output side by side (optionally only
 * those with a failure). The data can be exported as CSV.
 */
"use client"

import { CircleAlert, Download, Loader2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StatTile } from "@/components/common/stat-tile"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { useExperiments } from "@/features/run/hooks"
import type { ModelMetricsOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"

import { RESULTS_COPY } from "../copy"
import { downloadCsv, useCases, useResults } from "../hooks"
import { bestOn, brokenModels, isBest } from "../insights"
import { CaseView } from "./case-view"
import { ConfigPanel } from "./config-panel"
import { UnjudgedBanner } from "./unjudged-banner"
import { JudgingPanel } from "./judging-panel"
import { PassRateChart, percent, TradeoffTable } from "./tradeoff-table"

const FINISHED = new Set(["completed", "cancelled", "evaluating"])

export function ResultsStep({ projectId, experimentId }: { projectId: string; experimentId: string | null }) {
  const router = useRouter()
  const experiments = useExperiments(projectId)
  const finished = (experiments.data ?? []).filter((e) => FINISHED.has(e.status))
  const chosen = experimentId ?? finished.find((e) => e.origin === "manual")?.id ?? finished[0]?.id ?? null
  const results = useResults(projectId, chosen)
  const scored = Boolean(results.data?.evaluation_run)
  const [failedOnly, setFailedOnly] = useState(false)
  const cases = useCases(projectId, chosen, failedOnly, scored)
  const [exportError, setExportError] = useState<unknown>(null)

  if (experiments.data && finished.length === 0)
    return (
      <EmptyState
        title={RESULTS_COPY.title}
        description={RESULTS_COPY.none}
        action={
          <Link href={`/projects/${projectId}/run`} className="text-accent text-sm">
            →
          </Link>
        }
      />
    )
  const metrics = results.data?.models ?? []
  const current = (experiments.data ?? []).find((e) => e.id === chosen)
  const tiles = [
    {
      label: RESULTS_COPY.tiles.quality,
      model: bestOn(metrics, "quality"),
      show: (m: ModelMetricsOut) => percent(m.quality),
    },
    {
      label: RESULTS_COPY.tiles.passRate,
      model: bestOn(metrics, "pass_rate"),
      show: (m: ModelMetricsOut) => percent(m.pass_rate),
    },
    {
      label: RESULTS_COPY.tiles.cost,
      model: bestOn(metrics, "cost_per_call"),
      show: (m: ModelMetricsOut) => (m.cost_per_call === null ? "—" : formatCost(m.cost_per_call)),
    },
    {
      label: RESULTS_COPY.tiles.speed,
      model: bestOn(metrics, "latency_ms"),
      show: (m: ModelMetricsOut) => (m.latency_ms === null ? "—" : RESULTS_COPY.ms(m.latency_ms)),
    },
  ]
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <StepHeader
        projectId={projectId}
        step="results"
        title={RESULTS_COPY.title}
        description={RESULTS_COPY.subtitle}
        howItWorks={RESULTS_COPY.howItWorks}
        aside={
          <div className="flex w-80 flex-col gap-1.5">
            <Label htmlFor="experiment">{RESULTS_COPY.experiment}</Label>
            <NativeSelect
              id="experiment"
              value={chosen ?? ""}
              onChange={(e) => router.push(`/projects/${projectId}/results?experiment=${e.target.value}`)}
            >
              {finished.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name} · {new Date(e.created_at).toLocaleString()}
                </option>
              ))}
            </NativeSelect>
          </div>
        }
      />
      <ErrorMessage error={experiments.error ?? results.error ?? cases.error ?? exportError} />
      {results.data && !scored ? (
        <div className="bg-info-soft text-info-strong flex items-center gap-2 rounded-xl p-4 text-sm">
          <Loader2 className="size-4 animate-spin" />
          {RESULTS_COPY.notScored}
        </div>
      ) : null}
      {metrics.length ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {tiles.map((tile) => (
              <StatTile
                key={tile.label}
                label={tile.label}
                value={tile.model ? tile.show(tile.model) : RESULTS_COPY.tileNone}
                detail={tile.model?.model}
                winner={
                  tile.label === RESULTS_COPY.tiles.quality &&
                  tile.model !== null &&
                  isBest(metrics, tile.model, "quality")
                }
              />
            ))}
          </div>
          <UnjudgedBanner projectId={projectId} experiment={current} models={metrics} />
          {brokenModels(metrics).map((m) => (
            <div
              key={m.model_profile_id}
              className="bg-danger-soft text-danger-strong ring-danger/20 flex items-start gap-2 rounded-xl p-4 text-sm ring-1"
            >
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              {RESULTS_COPY.broken(m.model, m.failed_calls, m.cases)}
            </div>
          ))}
          <Section title={RESULTS_COPY.tableHeading} description={RESULTS_COPY.tableHint}>
            <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <TradeoffTable models={metrics} />
              <PassRateChart models={metrics} />
            </div>
          </Section>
        </>
      ) : null}
      {current ? (
        <ConfigPanel projectId={projectId} experiment={current} all={experiments.data ?? []} />
      ) : null}
      {scored && chosen && results.data?.evaluation_run ? (
        <JudgingPanel
          projectId={projectId}
          experimentId={chosen}
          versionId={results.data.evaluation_run.evaluator_set_version_id}
          cases={cases.data ?? []}
        />
      ) : null}
      {scored ? (
        <Section
          title={RESULTS_COPY.casesHeading}
          action={
            <>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={failedOnly} onCheckedChange={(checked) => setFailedOnly(checked)} />
                {RESULTS_COPY.failedOnly}
              </label>
              <Button
                variant="outline"
                size="sm"
                onClick={() => chosen && void downloadCsv(projectId, chosen).catch(setExportError)}
              >
                <Download />
                {RESULTS_COPY.export}
              </Button>
            </>
          }
        >
          {cases.isLoading ? (
            <div className="flex flex-col gap-3" aria-label={RESULTS_COPY.loadingCases}>
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : (cases.data ?? []).length === 0 ? (
            <p className="text-text-muted text-sm">{RESULTS_COPY.noCases}</p>
          ) : (
            <div className="flex flex-col gap-2">
              {(cases.data ?? []).map((item) => (
                <CaseView
                  key={item.dataset_item_id}
                  item={item}
                  projectId={projectId}
                  experimentId={chosen ?? ""}
                />
              ))}
            </div>
          )}
        </Section>
      ) : null}
      <PageActions>
        <Button
          size="lg"
          disabled={!scored}
          onClick={() => router.push(`/projects/${projectId}/improve?experiment=${chosen}`)}
        >
          {RESULTS_COPY.next}
        </Button>
      </PageActions>
    </div>
  )
}
