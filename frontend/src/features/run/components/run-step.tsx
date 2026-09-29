/**
 * Step 5, Run: the chosen models with runs and one parameter set each (controls a model
 * doesn't support are disabled), a budget cap, the cost preview, then "Start experiment"
 * and live progress.
 */
"use client"

import Link from "next/link"
import { useMemo, useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useModels } from "@/features/keys/hooks"
import { useCurrentVersion } from "@/features/tests/hooks"
import type { ExperimentCreate, ModelProfileOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { useDebounced } from "@/lib/use-debounced"

import { RUN_COPY } from "../copy"
import { useCancelExperiment, useExperimentEstimate, useExperiments, useStartExperiment } from "../hooks"
import { ProgressCard } from "./progress-card"

type Row = { include: boolean; runs: string; temperature: string; max_tokens: string }
const DEFAULT_ROW: Row = { include: true, runs: "1", temperature: "", max_tokens: "" }

function toBody(
  models: ModelProfileOut[],
  rows: Record<string, Row>,
  budget: string,
): ExperimentCreate | null {
  const chosen = models.filter((m) => (rows[m.id] ?? DEFAULT_ROW).include)
  if (chosen.length === 0) return null
  return {
    models: chosen.map((m) => {
      const row = rows[m.id] ?? DEFAULT_ROW
      const params: Record<string, number> = {}
      if (row.temperature.trim()) params.temperature = Number(row.temperature)
      if (row.max_tokens.trim()) params.max_tokens = Number(row.max_tokens)
      return { model_profile_id: m.id, runs: Math.min(5, Math.max(1, Number(row.runs) || 1)), params }
    }),
    budget_cap: budget.trim() ? budget.trim() : null,
    split_scope: "all",
  }
}

function Money({ value }: { value: string | null | undefined }) {
  return value === null || value === undefined ? (
    <span className="text-warning-strong">{RUN_COPY.unknown}</span>
  ) : (
    <span>{formatCost(value)}</span>
  )
}

export function RunStep({ projectId }: { projectId: string }) {
  const models = useModels(projectId)
  const version = useCurrentVersion(projectId)
  const experiments = useExperiments(projectId)
  const start = useStartExperiment(projectId)
  const cancel = useCancelExperiment(projectId)
  const [rows, setRows] = useState<Record<string, Row>>({})
  const [budget, setBudget] = useState("")
  const selected = useMemo(() => (models.data ?? []).filter((m) => m.is_selected), [models.data])
  const approved = version.data?.status === "approved"
  const body = useDebounced(approved ? toBody(selected, rows, budget) : null, 300)
  const estimate = useExperimentEstimate(projectId, body)
  const latest = experiments.data?.find((e) => e.origin === "manual")

  if (version.data !== undefined && !approved)
    return (
      <EmptyState
        title={RUN_COPY.title}
        description={RUN_COPY.notApproved}
        action={
          <Link href={`/projects/${projectId}/tests`} className="text-accent text-sm">
            →
          </Link>
        }
      />
    )
  if (models.data && selected.length === 0)
    return <EmptyState title={RUN_COPY.title} description={RUN_COPY.noModels} />

  const set = (id: string, field: keyof Row, value: string | boolean) =>
    setRows({ ...rows, [id]: { ...(rows[id] ?? DEFAULT_ROW), [field]: value } })
  const supports = (m: ModelProfileOut, name: string) => name in (m.parameters ?? {})
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <StepHeader
        step="run"
        title={RUN_COPY.title}
        description={RUN_COPY.subtitle}
        howItWorks={RUN_COPY.howItWorks}
      />
      <ErrorMessage error={models.error ?? version.error ?? experiments.error} />
      <Section number={1} title={RUN_COPY.modelsHeading} description={RUN_COPY.modelsHint}>
        <div className="border-border overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">{RUN_COPY.include}</TableHead>
                <TableHead>{RUN_COPY.columns.model}</TableHead>
                <TableHead className="w-24">{RUN_COPY.columns.runs}</TableHead>
                <TableHead className="w-32">{RUN_COPY.columns.temperature}</TableHead>
                <TableHead className="w-36">{RUN_COPY.columns.maxTokens}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {selected.map((m) => {
                const row = rows[m.id] ?? DEFAULT_ROW
                return (
                  <TableRow key={m.id}>
                    <TableCell>
                      <Checkbox
                        checked={row.include}
                        onCheckedChange={(checked) => set(m.id, "include", checked)}
                        aria-label={m.display_name}
                      />
                    </TableCell>
                    <TableCell>{m.display_name}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={1}
                        max={5}
                        value={row.runs}
                        aria-label={`${RUN_COPY.columns.runs} ${m.display_name}`}
                        onChange={(e) => set(m.id, "runs", e.target.value)}
                      />
                    </TableCell>
                    {(["temperature", "max_tokens"] as const).map((name) => (
                      <TableCell key={name}>
                        <Input
                          type="number"
                          step={name === "temperature" ? "0.1" : "1"}
                          min={name === "temperature" ? 0 : 1}
                          max={name === "temperature" ? (m.parameters?.temperature?.max ?? 2) : undefined}
                          disabled={!supports(m, name)}
                          title={supports(m, name) ? undefined : RUN_COPY.unsupported}
                          value={row[name]}
                          onChange={(e) => set(m.id, name, e.target.value)}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </Section>
      <Section number={2} title={RUN_COPY.previewHeading} description={RUN_COPY.previewHint}>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex max-w-xs flex-col gap-1.5">
            <Label htmlFor="budget">{RUN_COPY.budget}</Label>
            <Input
              id="budget"
              type="number"
              min={0}
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
            <p className="text-text-muted text-xs">{RUN_COPY.budgetHint}</p>
          </div>
          <div className="bg-subtle ring-border rounded-lg p-4 ring-1">
            <div className="flex flex-col gap-1.5 text-sm">
              <ErrorMessage error={estimate.error} />
              {estimate.data ? (
                <>
                  <p>{RUN_COPY.calls(estimate.data.calls, estimate.data.cases)}</p>
                  <p className="flex justify-between">
                    {RUN_COPY.generation} <Money value={estimate.data.generation_cost} />
                  </p>
                  <p className="flex justify-between">
                    {RUN_COPY.judge(estimate.data.judge_calls)} <Money value={estimate.data.judge_cost} />
                  </p>
                  <p className="border-border flex justify-between border-t pt-1.5 text-base font-semibold">
                    {RUN_COPY.total} <Money value={estimate.data.total_cost} />
                  </p>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </Section>
      {latest ? (
        <Section number={3} title={RUN_COPY.runningHeading} description={RUN_COPY.runningHint}>
          <ProgressCard
            projectId={projectId}
            experiment={latest}
            onCancel={() => cancel.mutate(latest.id)}
            cancelling={cancel.isPending}
          />
        </Section>
      ) : null}
      <PageActions summary={<ErrorMessage error={start.error ?? cancel.error} />}>
        <Button
          size="lg"
          disabled={!body || start.isPending || !estimate.data}
          onClick={() => body && start.mutate(body)}
        >
          {start.isPending ? RUN_COPY.starting : RUN_COPY.start}
        </Button>
      </PageActions>
    </div>
  )
}
