/**
 * Step 4, Test Cases: confirm the Task Spec, generate test cases (with the cost shown
 * first), review them by category with source badges, then approve. The one primary action
 * at the bottom right follows the stage: describe the task, generate, approve.
 */
"use client"

import Link from "next/link"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useCurrentPrompt } from "@/features/prompt/hooks"
import type { DatasetVersionOut, GenerationRequest } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { useDebounced } from "@/lib/use-debounced"

import { TESTS_COPY } from "../copy"
import {
  useCurrentVersion,
  useDraftSpec,
  useEstimate,
  useEvaluators,
  useGeneratorSuggestion,
  useItems,
  useStartGeneration,
  useTaskSpec,
  useVersionActions,
} from "../hooks"
import { CaseTable } from "./case-table"
import { EvaluatorCard } from "./evaluator-card"
import { modelKey, TaskSpecCard } from "./task-spec-card"

const DEFAULT_SIZE = 100

function Approved({ version }: { version: DatasetVersionOut }) {
  return (
    <Alert>
      <AlertDescription>
        <p className="font-medium">{TESTS_COPY.approvedTitle(version.version)}</p>
        <p>{TESTS_COPY.split(version.by_split.optimize ?? 0, version.by_split.holdout ?? 0)}</p>
      </AlertDescription>
    </Alert>
  )
}

export function TestsStep({ projectId }: { projectId: string }) {
  const prompt = useCurrentPrompt(projectId)
  const version = useCurrentVersion(projectId)
  const suggestion = useGeneratorSuggestion(projectId)
  const draftSpec = useDraftSpec(projectId)
  const start = useStartGeneration(projectId)
  const [draftId, setDraftId] = useState<string | null>(null)
  const specId = draftId ?? version.data?.task_spec_id ?? null
  const spec = useTaskSpec(projectId, specId)
  const [picked, setChosen] = useState<string | null>(null)
  const [size, setSize] = useState(String(DEFAULT_SIZE))
  const [goldenOnly, setGoldenOnly] = useState(false)

  const models = useMemo(() => suggestion.data?.candidates ?? [], [suggestion.data])
  const preferred = spec.data?.generator_credential_id
    ? `${spec.data.generator_credential_id}|${spec.data.generator_model}`
    : suggestion.data?.suggested
      ? modelKey(suggestion.data.suggested)
      : ""
  const chosen = picked ?? preferred

  const current = version.data ?? null
  const running = current?.generation?.status === "running"
  const frozen = current?.status === "approved"
  const items = useItems(projectId, current?.id, running)
  const evaluators = useEvaluators(projectId, current?.id, Boolean(current?.evaluator_set_version_id))
  const actions = useVersionActions(projectId, current?.id ?? "")
  const confirmed = spec.data?.status === "confirmed"
  const hasGolden = (current?.by_source.golden?.total ?? 0) > 0
  const request = useDebounced<GenerationRequest | null>(
    confirmed && specId
      ? { task_spec_id: specId, target_size: Number(size) || DEFAULT_SIZE, golden_only: goldenOnly }
      : null,
    300,
  )
  const estimate = useEstimate(projectId, frozen || running ? null : request)

  if (prompt.data === null)
    return (
      <EmptyState
        title={TESTS_COPY.title}
        description={TESTS_COPY.noPrompt}
        action={
          <Link href={`/projects/${projectId}/prompt`} className="text-accent text-sm">
            →
          </Link>
        }
      />
    )
  if (suggestion.data && models.length === 0)
    return (
      <EmptyState
        title={TESTS_COPY.title}
        description={TESTS_COPY.noModels}
        action={
          <Link href={`/projects/${projectId}/keys`} className="text-accent text-sm">
            →
          </Link>
        }
      />
    )

  async function describe() {
    const [credentialId, model] = chosen.split("|")
    if (!prompt.data || !credentialId || !model) return
    const drafted = await draftSpec.mutateAsync({
      prompt_version_id: prompt.data.latest_version.id,
      credential_id: credentialId,
      model,
    })
    setDraftId(drafted.id)
  }

  async function generate() {
    if (!request) return
    await start.mutateAsync(request)
    setDraftId(null)
  }

  async function approve() {
    await actions.approve.mutateAsync()
    toast.success(TESTS_COPY.approved)
  }

  const total = current?.item_count ?? 0
  const drafts = Object.values(current?.by_source ?? {}).reduce((sum, group) => sum + (group?.draft ?? 0), 0)
  const generated = Boolean(current?.evaluator_set_version_id) && current?.task_spec_id === specId
  const primary = frozen ? (
    <Button size="lg" disabled>
      {TESTS_COPY.approvedTitle(current?.version ?? 1)}
    </Button>
  ) : !spec.data ? (
    <Button
      size="lg"
      onClick={() => void describe().catch(() => undefined)}
      disabled={!chosen || draftSpec.isPending}
    >
      {draftSpec.isPending ? TESTS_COPY.describing : TESTS_COPY.describe}
    </Button>
  ) : generated && total > 0 && !running ? (
    <Button
      size="lg"
      onClick={() => void approve().catch(() => undefined)}
      disabled={drafts > 0 || actions.approve.isPending}
    >
      {actions.approve.isPending ? TESTS_COPY.approving : TESTS_COPY.approve}
    </Button>
  ) : (
    <Button
      size="lg"
      onClick={() => void generate().catch(() => undefined)}
      disabled={!confirmed || running || start.isPending}
    >
      {running ? TESTS_COPY.generating : TESTS_COPY.generate}
    </Button>
  )

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold">{TESTS_COPY.title}</h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm">{TESTS_COPY.subtitle}</p>
      </div>
      <ErrorMessage
        error={prompt.error ?? version.error ?? suggestion.error ?? spec.error ?? draftSpec.error}
      />
      {frozen && current ? <Approved version={current} /> : null}
      <TaskSpecCard
        projectId={projectId}
        spec={spec.data ?? null}
        models={models}
        chosen={chosen}
        onChoose={(key) => {
          setChosen(key)
          setDraftId(null)
        }}
        onConfirmed={() => undefined}
        locked={frozen || running}
      />
      {confirmed && !frozen ? (
        <Card>
          <CardHeader>
            <CardTitle>{TESTS_COPY.generateHeading}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-wrap items-end gap-6">
              <div className="flex w-40 flex-col gap-1.5">
                <Label htmlFor="size">{TESTS_COPY.size}</Label>
                <Input
                  id="size"
                  type="number"
                  min={20}
                  max={1000}
                  value={size}
                  disabled={goldenOnly}
                  onChange={(e) => setSize(e.target.value)}
                />
              </div>
              {hasGolden ? (
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={goldenOnly} onCheckedChange={(checked) => setGoldenOnly(checked)} />
                  {TESTS_COPY.goldenOnly}
                </label>
              ) : null}
            </div>
            <p className="text-muted-foreground text-xs">{TESTS_COPY.sizeHint}</p>
            {estimate.data && !goldenOnly ? (
              <p className="text-sm">
                {TESTS_COPY.estimate(estimate.data.cases_to_generate, estimate.data.calls)} ·{" "}
                {TESTS_COPY.estimatedCost}:{" "}
                {estimate.data.price_known ? (
                  <span className="font-medium">{formatCost(estimate.data.cost)}</span>
                ) : (
                  <span className="text-warning">{TESTS_COPY.priceUnknown}</span>
                )}
              </p>
            ) : null}
            <ErrorMessage error={estimate.error ?? start.error} />
            {running ? <p className="text-sm">{TESTS_COPY.progress(total)}</p> : null}
            {current?.generation?.status === "failed" ? (
              <p className="text-destructive text-sm">
                {TESTS_COPY.failed}: {String(current.generation.message ?? "")}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      {current && total > 0 ? (
        <section className="flex flex-col gap-3">
          <div>
            <h3 className="text-base font-medium">{TESTS_COPY.tableHeading}</h3>
            <p className="text-muted-foreground text-sm">{TESTS_COPY.reviewHint}</p>
          </div>
          {current.warnings.map((warning) => (
            <p key={warning} className="text-warning text-sm">
              {warning}
            </p>
          ))}
          <CaseTable projectId={projectId} versionId={current.id} items={items.data ?? []} frozen={frozen} />
        </section>
      ) : null}
      {current && evaluators.data ? (
        <EvaluatorCard projectId={projectId} versionId={current.id} set={evaluators.data} frozen={frozen} />
      ) : null}
      <PageActions
        summary={
          <div className="flex flex-col gap-1">
            {total > 0 ? <span>{TESTS_COPY.summary(total, drafts)}</span> : null}
            <ErrorMessage error={actions.approve.error} />
          </div>
        }
      >
        {primary}
      </PageActions>
    </div>
  )
}
