/**
 * Step 6, Results: pick a finished experiment, then the tradeoff table, one pass-rate
 * chart, and the test cases with every model's output side by side (optionally only
 * those with a failure). The data can be exported as CSV.
 */
"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { useExperiments } from "@/features/run/hooks"

import { RESULTS_COPY } from "../copy"
import { downloadCsv, useCases, useResults } from "../hooks"
import { CaseView } from "./case-view"
import { PassRateChart, TradeoffTable } from "./tradeoff-table"

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
  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">{RESULTS_COPY.title}</h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm">{RESULTS_COPY.subtitle}</p>
      </div>
      <ErrorMessage error={experiments.error ?? results.error ?? cases.error ?? exportError} />
      <div className="flex max-w-md flex-col gap-1.5">
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
      {results.data && !scored ? <p className="text-sm">{RESULTS_COPY.notScored}</p> : null}
      {results.data?.models.length ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <TradeoffTable models={results.data.models} />
          <PassRateChart models={results.data.models} />
        </div>
      ) : null}
      {scored ? (
        <section className="flex flex-col gap-3">
          <div className="flex items-center gap-4">
            <h3 className="text-base font-medium">{RESULTS_COPY.casesHeading}</h3>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={failedOnly} onCheckedChange={(checked) => setFailedOnly(checked)} />
              {RESULTS_COPY.failedOnly}
            </label>
            <Button
              variant="outline"
              size="sm"
              className="ml-auto"
              onClick={() => chosen && void downloadCsv(projectId, chosen).catch(setExportError)}
            >
              {RESULTS_COPY.export}
            </Button>
          </div>
          {(cases.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-sm">{RESULTS_COPY.noCases}</p>
          ) : null}
          {(cases.data ?? []).map((item) => (
            <CaseView key={item.dataset_item_id} item={item} />
          ))}
        </section>
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
