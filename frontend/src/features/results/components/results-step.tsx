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
import { PageIntro } from "@/components/common/page-intro"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useExperiments } from "@/features/run/hooks"
import { ALL_PROJECT_PAGES } from "@/lib/nav"

import { RESULTS_COPY, TABS_COPY } from "../copy"
import { downloadCsv, scoringInProgress, useCases, useResults } from "../hooks"
import { useCandidateFor, useSaveCandidate } from "@/features/improve/hooks"
import { unfairReasons } from "@/lib/fairness"

import { brokenModels } from "../insights"
import { CaseView } from "./case-view"
import { ConfigPanel } from "./config-panel"
import { UnjudgedBanner } from "./unjudged-banner"
import { AgreementPanel } from "./agreement-panel"
import { BlindNotice, BlindToggle } from "./blind-toggle"
import { ProofExplainer } from "./proof-explainer"
import { promptTag } from "@/features/prompts-choice/domain"
import { JudgingPanel } from "./judging-panel"
import { CompareTab } from "./compare-tab"
import { SummaryTab } from "./summary-tab"

const FINISHED = new Set(["completed", "cancelled", "evaluating"])

export function ResultsStep({ projectId, experimentId }: { projectId: string; experimentId: string | null }) {
  const router = useRouter()
  const experiments = useExperiments(projectId)
  const finished = (experiments.data ?? []).filter((e) => FINISHED.has(e.status))
  const chosen = experimentId ?? finished.find((e) => e.origin === "manual")?.id ?? finished[0]?.id ?? null
  const results = useResults(projectId, chosen)
  const scored = Boolean(results.data?.evaluation_run)
  const [failedOnly, setFailedOnly] = useState(false)
  const [blind, setBlind] = useState(false)
  const cases = useCases(
    projectId,
    chosen,
    failedOnly,
    scored,
    results.data?.evaluation_run?.id ?? null,
    blind,
  )
  const [tab, setTab] = useState("summary")
  const [exportError, setExportError] = useState<unknown>(null)
  const optimizing = (experiments.data ?? []).find((e) => e.id === chosen)?.origin === "optimization"
  const candidate = useCandidateFor(projectId, optimizing ? chosen : null)
  const saveCandidate = useSaveCandidate(projectId)

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
  const unfair = current ? unfairReasons(current) : []
  const ranked = unfair.length === 0
  const page = ALL_PROJECT_PAGES.find((p) => p.key === "results")!
  const alerts = (
    <>
      {results.data && !scored ? (
        <div className="bg-info-soft text-info-strong flex items-center gap-2 rounded-xl p-4 text-sm">
          <Loader2 className="size-4 animate-spin" />
          {RESULTS_COPY.notScored}
        </div>
      ) : null}
      {results.data && scored && scoringInProgress(results.data) ? (
        <div className="bg-info-soft text-info-strong flex items-center gap-2 rounded-xl p-4 text-sm">
          <Loader2 className="size-4 animate-spin" />
          {RESULTS_COPY.scoringAgain}
        </div>
      ) : null}
      {unfair.length ? (
        <div className="bg-marigold-soft text-marigold-strong ring-marigold/30 flex items-start gap-2 rounded-xl p-4 text-sm ring-1">
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-semibold">{RESULTS_COPY.unfairTitle}</p>
            {unfair.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
            <p>{RESULTS_COPY.unfairAdvice}</p>
          </div>
        </div>
      ) : null}
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
    </>
  )
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <PageIntro
        storageKey="results"
        title={page.label}
        what="Quality, cost and speed for every model that ran, side by side."
        whenToUse="a test has finished and you want to know which model to use"
        youGet="the best model, how sure we are, and every answer behind the numbers"
        learnMore="results"
        hasContent={metrics.length > 0}
      />
      <div className="flex max-w-md flex-col gap-1.5">
        <Label htmlFor="experiment">{RESULTS_COPY.experiment}</Label>
        <NativeSelect
          id="experiment"
          value={chosen ?? ""}
          onChange={(e) => router.push(`/projects/${projectId}/results?experiment=${e.target.value}`)}
        >
          {finished.map((e) => (
            <option key={e.id} value={e.id}>
              {promptTag(e, finished)}
              {e.name} · {new Date(e.created_at).toLocaleString()}
            </option>
          ))}
        </NativeSelect>
      </div>
      <ErrorMessage error={experiments.error ?? results.error ?? cases.error ?? exportError} />
      {candidate.data ? (
        <div className="bg-subtle ring-border flex flex-wrap items-center gap-3 rounded-xl p-4 text-sm ring-1">
          <p className="min-w-0 flex-1">
            {RESULTS_COPY.candidateTest(candidate.data.strategy)} {RESULTS_COPY.candidateUse}
          </p>
          <Button
            disabled={saveCandidate.isPending}
            onClick={() =>
              void saveCandidate
                .mutateAsync({
                  sessionId: candidate.data?.session_id ?? "",
                  candidateId: candidate.data?.candidate_id ?? "",
                  run: true,
                })
                .then((done) => {
                  if (done.started_experiment_id)
                    router.push(`/projects/${projectId}/results?experiment=${done.started_experiment_id}`)
                })
                .catch(() => undefined)
            }
          >
            {RESULTS_COPY.candidateButton}
          </Button>
        </div>
      ) : null}
      {alerts}
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <div className="overflow-x-auto">
          <TabsList aria-label={TABS_COPY.label} className="h-auto min-h-10 w-max">
            <TabsTrigger value="summary" className="min-h-9 px-3">
              {TABS_COPY.summary}
            </TabsTrigger>
            <TabsTrigger value="compare" className="min-h-9 px-3">
              {TABS_COPY.compare}
            </TabsTrigger>
            <TabsTrigger value="answers" className="min-h-9 px-3">
              {TABS_COPY.answers}
            </TabsTrigger>
            <TabsTrigger value="details" className="min-h-9 px-3">
              {TABS_COPY.details}
            </TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="summary" className="pt-2">
          {metrics.length && chosen ? (
            <SummaryTab
              projectId={projectId}
              experimentId={chosen}
              models={metrics}
              ranked={ranked}
              scored={scored}
            />
          ) : (
            <p className="text-text-muted text-sm">{RESULTS_COPY.notScored}</p>
          )}
        </TabsContent>
        <TabsContent value="compare" className="pt-2">
          {metrics.length ? (
            <CompareTab models={metrics} ranked={ranked} />
          ) : (
            <p className="text-text-muted text-sm">{RESULTS_COPY.notScored}</p>
          )}
        </TabsContent>
        <TabsContent value="answers" className="flex flex-col gap-6 pt-2">
          {scored ? (
            <Section
              title={RESULTS_COPY.casesHeading}
              action={
                <>
                  <label className="flex min-h-10 items-center gap-2 text-sm">
                    <Checkbox
                      checked={failedOnly && !blind}
                      disabled={blind}
                      onCheckedChange={(checked) => setFailedOnly(checked)}
                    />
                    {RESULTS_COPY.failedOnly}
                  </label>
                  <BlindToggle blind={blind} onChange={setBlind} />
                </>
              }
            >
              {blind ? <BlindNotice /> : null}
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
          ) : (
            <p className="text-text-muted text-sm">{RESULTS_COPY.notScored}</p>
          )}
        </TabsContent>
        <TabsContent value="details" className="flex flex-col gap-6 pt-2">
          <ProofExplainer projectId={projectId} />
          {current ? (
            <Accordion>
              <AccordionItem value="config">
                <AccordionTrigger className="min-h-10">
                  Run configuration and compare two runs
                </AccordionTrigger>
                <AccordionContent>
                  <ConfigPanel projectId={projectId} experiment={current} all={experiments.data ?? []} />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          ) : null}
          {scored && chosen && results.data?.evaluation_run ? (
            <JudgingPanel
              projectId={projectId}
              experimentId={chosen}
              versionId={results.data.evaluation_run.evaluator_set_version_id}
              cases={cases.data ?? []}
            />
          ) : null}
          {scored && chosen ? <AgreementPanel projectId={projectId} experimentId={chosen} /> : null}
          {scored ? (
            <div>
              <Button
                variant="outline"
                size="lg"
                onClick={() => chosen && void downloadCsv(projectId, chosen).catch(setExportError)}
              >
                <Download />
                {RESULTS_COPY.export}
              </Button>
            </div>
          ) : null}
        </TabsContent>
      </Tabs>
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
