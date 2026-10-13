/**
 * Step 4, Test Cases: confirm the Task Spec, generate test cases (with the cost shown
 * first), review them by category with source badges, then approve. The one primary action
 * at the bottom right follows the stage: describe the task, generate, approve.
 */
"use client"

import { CircleCheck, Loader2 } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useCurrentPrompt } from "@/features/prompt/hooks"
import type { DatasetVersionOut, GenerationRequest } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { useDebounced } from "@/lib/use-debounced"

import { TESTS_COPY } from "../copy"
import {
  useCancelGeneration,
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

const DEFAULT_SIZE = 30

function Approved({ version }: { version: DatasetVersionOut }) {
  return (
    <div className="bg-success-soft ring-success/25 text-success-strong flex items-start gap-3 rounded-xl p-4 ring-1">
      <CircleCheck className="mt-0.5 size-5 shrink-0" />
      <div className="text-sm">
        <p className="font-semibold">{TESTS_COPY.approvedTitle(version.version)}</p>
        <p>{TESTS_COPY.split(version.by_split.optimize ?? 0, version.by_split.holdout ?? 0)}</p>
      </div>
    </div>
  )
}

function Counts({ total, drafts }: { total: number; drafts: number }) {
  return (
    <div className="flex flex-wrap gap-2">
      <StatusBadge tone="neutral">
        {TESTS_COPY.total}: {total}
      </StatusBadge>
      {drafts ? (
        <StatusBadge tone="warning">
          {TESTS_COPY.needReview}: {drafts}
        </StatusBadge>
      ) : null}
      <StatusBadge tone="success">
        {TESTS_COPY.reviewed}: {total - drafts}
      </StatusBadge>
    </div>
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
  const [budget, setBudget] = useState<string | null>(null)
  const [accepted, setAccepted] = useState(false)

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
  const cancel = useCancelGeneration(projectId, current?.id ?? "")
  const confirmed = spec.data?.status === "confirmed"
  const hasGolden = (current?.by_source.golden?.total ?? 0) > 0
  const sizeRequest =
    confirmed && specId
      ? {
          task_spec_id: specId,
          target_size: Number(size) || DEFAULT_SIZE,
          golden_only: goldenOnly,
          accept_cost: false,
        }
      : null
  const settledRequest = useDebounced(sizeRequest, 300)
  const estimate = useEstimate(projectId, frozen || running ? null : settledRequest)
  const cost = estimate.data?.cost ? Number(estimate.data.cost) : 0
  const suggestedBudget = cost > 0 ? Math.max(0.05, cost * 2).toFixed(2) : ""
  const budgetValue = budget ?? suggestedBudget
  const needsConfirm = Boolean(estimate.data?.needs_confirmation) && !goldenOnly
  const request: GenerationRequest | null = sizeRequest
    ? {
        ...sizeRequest,
        budget_cap: goldenOnly || Number(budgetValue) <= 0 ? undefined : budgetValue,
        accept_cost: needsConfirm && accepted,
      }
    : null

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
      disabled={!confirmed || running || start.isPending || (needsConfirm && !accepted)}
    >
      {running ? TESTS_COPY.generating : TESTS_COPY.generate}
    </Button>
  )

  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <StepHeader
        projectId={projectId}
        step="tests"
        title={TESTS_COPY.title}
        description={TESTS_COPY.subtitle}
        howItWorks={TESTS_COPY.howItWorks}
      />
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
      {!frozen ? (
        <Section
          number={2}
          title={TESTS_COPY.generateHeading}
          description={TESTS_COPY.generateHint}
          muted={!confirmed}
          badge={
            running ? (
              <StatusBadge tone="info" icon={<Loader2 className="animate-spin" />}>
                {TESTS_COPY.generating}
              </StatusBadge>
            ) : current?.generation?.status === "failed" ? (
              <StatusBadge tone="danger">{TESTS_COPY.failed}</StatusBadge>
            ) : current?.generation?.status === "stopped" ? (
              <StatusBadge tone="warning">{TESTS_COPY.stoppedBadge}</StatusBadge>
            ) : null
          }
          action={
            running ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void cancel.mutateAsync().catch(() => undefined)}
                disabled={cancel.isPending || Boolean(current?.generation?.cancel_requested)}
              >
                {cancel.isPending || current?.generation?.cancel_requested
                  ? TESTS_COPY.stopping
                  : TESTS_COPY.stop}
              </Button>
            ) : null
          }
        >
          <div className="flex flex-wrap items-end gap-6">
            <div className="flex w-40 flex-col gap-1.5">
              <Label htmlFor="size">{TESTS_COPY.size}</Label>
              <Input
                id="size"
                type="number"
                min={5}
                max={1000}
                value={size}
                disabled={goldenOnly || !confirmed}
                onChange={(e) => {
                  setSize(e.target.value)
                  setAccepted(false)
                }}
              />
            </div>
            <div className="flex w-48 flex-col gap-1.5">
              <Label htmlFor="budget">{TESTS_COPY.budget}</Label>
              <Input
                id="budget"
                type="number"
                min={0}
                step="0.01"
                value={budgetValue}
                disabled={goldenOnly || !confirmed}
                onChange={(e) => setBudget(e.target.value)}
              />
            </div>
            {hasGolden ? (
              <label className="flex items-center gap-2 pb-1.5 text-sm">
                <Checkbox checked={goldenOnly} onCheckedChange={(checked) => setGoldenOnly(checked)} />
                {TESTS_COPY.goldenOnly}
              </label>
            ) : null}
            {estimate.data && !goldenOnly && confirmed ? (
              <div className="bg-subtle ring-border ml-auto flex items-center gap-4 rounded-lg px-4 py-2 text-sm ring-1">
                <span className="text-text-secondary">
                  {TESTS_COPY.estimate(estimate.data.cases_to_generate, estimate.data.calls)}
                </span>
                <span>
                  {TESTS_COPY.estimatedCost}:{" "}
                  {estimate.data.price_known ? (
                    <span className="font-semibold">{formatCost(estimate.data.cost)}</span>
                  ) : (
                    <span className="text-warning-strong">{TESTS_COPY.priceUnknown}</span>
                  )}
                </span>
              </div>
            ) : null}
          </div>
          <p className="text-text-muted text-xs">
            {TESTS_COPY.sizeHint} {TESTS_COPY.budgetHint}
          </p>
          {needsConfirm && confirmed ? (
            <label className="bg-warning-soft text-warning-strong ring-warning/25 flex items-center gap-2 rounded-lg p-3 text-sm ring-1">
              <Checkbox checked={accepted} onCheckedChange={(checked) => setAccepted(checked)} />
              {estimate.data?.price_known
                ? TESTS_COPY.confirmCost(formatCost(estimate.data.cost))
                : TESTS_COPY.confirmCostUnknown}
            </label>
          ) : null}
          <ErrorMessage error={estimate.error ?? start.error} />
          {running ? <p className="text-sm">{TESTS_COPY.progress(total)}</p> : null}
          {current?.generation?.status === "failed" ? (
            <p className="text-danger-strong text-sm">{String(current.generation.message ?? "")}</p>
          ) : null}
          {current?.generation?.status === "stopped" ? (
            <p className="text-warning-strong text-sm">{String(current.generation.message ?? "")}</p>
          ) : null}
        </Section>
      ) : null}
      {current && total > 0 ? (
        <Section
          number={frozen ? 2 : 3}
          title={TESTS_COPY.tableHeading}
          description={TESTS_COPY.reviewHint}
          action={<Counts total={total} drafts={drafts} />}
        >
          {current.warnings.map((warning) => (
            <p
              key={warning}
              className="bg-warning-soft text-warning-strong ring-warning/25 rounded-lg p-3 text-sm ring-1"
            >
              {warning}
            </p>
          ))}
          <CaseTable projectId={projectId} versionId={current.id} items={items.data ?? []} frozen={frozen} />
        </Section>
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
