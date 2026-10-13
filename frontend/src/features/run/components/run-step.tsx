/**
 * Step 5, Run: the chosen models with runs and one parameter set each (controls a model
 * doesn't support are disabled), a budget cap, the cost preview, then "Start experiment"
 * and live progress.
 */
"use client"

import Link from "next/link"
import { Fragment, useMemo, useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useModels } from "@/features/keys/hooks"
import { useCurrentPrompt, usePromptVersions } from "@/features/prompt/hooks"
import { JudgePicker, useChosenJudge } from "@/features/results/components/judge-picker"
import { DatasetWarnings } from "@/components/common/dataset-warnings"
import { useCurrentVersion } from "@/features/tests/hooks"
import type { ModelProfileOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { useDebounced } from "@/lib/use-debounced"

import { RUN_COPY } from "../copy"
import { useCancelExperiment, useExperimentEstimate, useExperiments, useStartExperiment } from "../hooks"
import {
  ADVANCED,
  advancedCount,
  DEFAULT_RUNS,
  defaultRow,
  problems,
  supports,
  toBody,
  warning,
  MAX_RUNS,
  type Row,
  randomnessOf,
  withRandomness,
} from "../settings"
import { ProgressCard } from "./progress-card"

function Money({ value }: { value: string | null | undefined }) {
  return value === null || value === undefined ? (
    <span className="text-warning-strong">{RUN_COPY.unknown}</span>
  ) : (
    <span>{formatCost(value)}</span>
  )
}

function AdvancedFields({
  model,
  row,
  wrong,
  onChange,
}: {
  model: ModelProfileOut
  row: Row
  wrong: Partial<Record<string, string>>
  onChange: (field: Exclude<keyof Row, "include">, value: string) => void
}) {
  const shown = ADVANCED.filter((name) => supports(model, name))
  if (shown.length === 0) return <p className="text-text-muted text-xs">{RUN_COPY.unsupported}</p>
  return (
    <div className="flex flex-col gap-3">
      <p className="text-text-muted text-xs">{RUN_COPY.advancedHint}</p>
      <div className="grid gap-4 md:grid-cols-3">
        {shown.map((name) => {
          const id = `${model.id}-${name}`
          const { label, hint } = RUN_COPY.fields[name]
          return (
            <div key={name} className="flex flex-col gap-1.5">
              <Label htmlFor={id}>{label}</Label>
              {name === "stop" ? (
                <Textarea
                  id={id}
                  rows={2}
                  value={row.stop}
                  aria-invalid={wrong.stop ? true : undefined}
                  onChange={(e) => onChange("stop", e.target.value)}
                />
              ) : (
                <Input
                  id={id}
                  type="number"
                  step={name === "top_p" || name.endsWith("penalty") ? "0.1" : "1"}
                  min={model.parameters?.[name]?.min ?? undefined}
                  max={model.parameters?.[name]?.max ?? undefined}
                  value={row[name]}
                  aria-invalid={wrong[name] ? true : undefined}
                  onChange={(e) => onChange(name, e.target.value)}
                />
              )}
              <p className="text-text-muted text-xs">{hint}</p>
            </div>
          )
        })}
      </div>
    </div>
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
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [pickedJudge, setPickedJudge] = useState("")
  const [pickedVersion, setPickedVersion] = useState("")
  const prompt = useCurrentPrompt(projectId)
  const versions = usePromptVersions(projectId, prompt.data?.id ?? null)
  const judge = useChosenJudge(projectId, pickedJudge)
  const selected = useMemo(() => (models.data ?? []).filter((m) => m.is_selected), [models.data])
  const approved = version.data?.status === "approved"
  const plan = approved ? toBody(selected, rows, budget) : null
  const promptVersion = pickedVersion || null
  const body = useDebounced(
    plan ? { ...plan, ...(judge ? { judge } : {}), prompt_version_id: promptVersion } : plan,
    300,
  )
  const randomness = randomnessOf(selected, rows)
  function chooseRandomness(mode: "repeatable" | "default") {
    setRows(
      Object.fromEntries(selected.map((m) => [m.id, withRandomness(m, rows[m.id] ?? defaultRow(m), mode)])),
    )
  }
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

  const setAllRuns = (value: string) =>
    setRows(
      Object.fromEntries(selected.map((m) => [m.id, { ...(rows[m.id] ?? defaultRow(m)), runs: value }])),
    )
  const runsAll = selected.length ? (rows[selected[0].id] ?? defaultRow(selected[0])).runs : DEFAULT_RUNS
  const anyWrong = selected.some((m) => Object.keys(problems(m, rows[m.id] ?? defaultRow(m))).length > 0)
  const set = (m: ModelProfileOut, field: keyof Row, value: string | boolean) =>
    setRows({ ...rows, [m.id]: { ...(rows[m.id] ?? defaultRow(m)), [field]: value } })
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <StepHeader
        projectId={projectId}
        step="run"
        title={RUN_COPY.title}
        description={RUN_COPY.subtitle}
        howItWorks={RUN_COPY.howItWorks}
      />
      <ErrorMessage error={models.error ?? version.error ?? experiments.error} />
      <DatasetWarnings projectId={projectId} />
      <div className="bg-subtle ring-border rounded-xl p-4 text-sm ring-1">
        <p className="font-semibold">{RUN_COPY.summaryHeading}</p>
        <p>
          {RUN_COPY.summary(
            version.data?.item_count ?? 0,
            selected.map((m) => m.display_name).join(", "),
            versions.data?.find((v) => v.id === pickedVersion)
              ? `V${versions.data?.find((v) => v.id === pickedVersion)?.version}`
              : `V${versions.data?.[0]?.version ?? 1} (latest)`,
            estimate.data?.judge_model ?? null,
          )}{" "}
          {estimate.data?.total_cost ? <Money value={estimate.data.total_cost} /> : null}
        </p>
      </div>
      <Section
        number={1}
        title={RUN_COPY.modelsHeading}
        description={`${RUN_COPY.modelsHint} ${RUN_COPY.modelsHint2}`}
      >
        <div className="grid gap-5 md:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="prompt-version">{RUN_COPY.versionLabel}</Label>
            <NativeSelect
              id="prompt-version"
              value={pickedVersion}
              onChange={(e) => setPickedVersion(e.target.value)}
              className="h-9 max-w-md"
            >
              {(versions.data ?? []).map((v, i) => (
                <option key={v.id} value={i === 0 ? "" : v.id}>
                  {i === 0
                    ? RUN_COPY.versionLatest(v.version)
                    : RUN_COPY.versionOption(v.version, v.change_reason)}
                </option>
              ))}
            </NativeSelect>
            <p className="text-text-muted text-xs">{RUN_COPY.versionHint}</p>
          </div>
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">{RUN_COPY.randomnessLabel}</legend>
            {(["repeatable", "default"] as const).map((mode) => (
              <label key={mode} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="randomness"
                  className="accent-lagoon mt-1"
                  checked={randomness === mode}
                  onChange={() => chooseRandomness(mode)}
                />
                <span>
                  <span className="font-medium">{RUN_COPY.randomness[mode].label}</span>
                  <span className="text-text-muted block text-xs">{RUN_COPY.randomness[mode].hint}</span>
                </span>
              </label>
            ))}
            {randomness === "custom" ? (
              <p className="text-text-muted text-xs">{RUN_COPY.randomness.custom}</p>
            ) : null}
            <p className="text-text-muted text-xs">{RUN_COPY.replicabilityHint}</p>
          </fieldset>
        </div>
        <div className="flex max-w-xs flex-col gap-1.5">
          <Label htmlFor="runs-all">{RUN_COPY.runsAll}</Label>
          <Input
            id="runs-all"
            type="number"
            min={1}
            max={MAX_RUNS}
            value={runsAll}
            onChange={(e) => setAllRuns(e.target.value)}
          />
          <p className="text-text-muted text-xs">{RUN_COPY.runsAllHint}</p>
        </div>
        <details open={anyWrong || undefined} className="group">
          <summary className="text-accent cursor-pointer text-sm">{RUN_COPY.expert}</summary>
          <div className="mt-3">
            <div className="border-border overflow-hidden rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">{RUN_COPY.include}</TableHead>
                    <TableHead>{RUN_COPY.columns.model}</TableHead>
                    <TableHead className="w-24">{RUN_COPY.columns.runs}</TableHead>
                    <TableHead className="w-32">{RUN_COPY.columns.temperature}</TableHead>
                    <TableHead className="w-36">{RUN_COPY.columns.maxTokens}</TableHead>
                    <TableHead className="w-44">{RUN_COPY.advanced}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {selected.map((m) => {
                    const row = rows[m.id] ?? defaultRow(m)
                    const wrong = problems(m, row)
                    const heads = warning(m, row)
                    const count = advancedCount(m, row)
                    return (
                      <Fragment key={m.id}>
                        <TableRow>
                          <TableCell>
                            <Checkbox
                              checked={row.include}
                              onCheckedChange={(checked) => set(m, "include", checked)}
                              aria-label={m.display_name}
                            />
                          </TableCell>
                          <TableCell>{m.display_name}</TableCell>
                          <TableCell>
                            <Input
                              type="number"
                              min={1}
                              max={MAX_RUNS}
                              value={row.runs}
                              aria-label={`${RUN_COPY.columns.runs} ${m.display_name}`}
                              aria-invalid={wrong.runs ? true : undefined}
                              title={wrong.runs}
                              onChange={(e) => set(m, "runs", e.target.value)}
                            />
                          </TableCell>
                          {(["temperature", "max_tokens"] as const).map((name) => (
                            <TableCell key={name}>
                              <Input
                                type="number"
                                step={name === "temperature" ? "0.1" : "1"}
                                min={m.parameters?.[name]?.min ?? undefined}
                                max={m.parameters?.[name]?.max ?? undefined}
                                disabled={!supports(m, name)}
                                title={supports(m, name) ? wrong[name] : RUN_COPY.unsupported}
                                aria-label={`${RUN_COPY.columns[name === "temperature" ? "temperature" : "maxTokens"]} ${m.display_name}`}
                                aria-invalid={wrong[name] ? true : undefined}
                                value={row[name]}
                                onChange={(e) => set(m, name, e.target.value)}
                              />
                            </TableCell>
                          ))}
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-expanded={open[m.id] ?? false}
                              onClick={() => setOpen({ ...open, [m.id]: !open[m.id] })}
                            >
                              {RUN_COPY.advancedSet(count)} {open[m.id] ? "▴" : "▾"}
                            </Button>
                          </TableCell>
                        </TableRow>
                        {open[m.id] ? (
                          <TableRow>
                            <TableCell colSpan={6} className="bg-subtle">
                              <AdvancedFields
                                model={m}
                                row={row}
                                wrong={wrong}
                                onChange={(f, v) => set(m, f, v)}
                              />
                            </TableCell>
                          </TableRow>
                        ) : null}
                        {Object.keys(wrong).length > 0 || heads ? (
                          <TableRow>
                            <TableCell colSpan={6} className="py-1 text-xs">
                              {Object.entries(wrong).map(([field, message]) => (
                                <p key={field} className="text-danger-strong">
                                  {m.display_name}: {field.replaceAll("_", " ")} — {message}
                                </p>
                              ))}
                              {heads ? <p className="text-warning-strong">{heads}</p> : null}
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </Fragment>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          </div>
        </details>
      </Section>
      <Section number={2} title={RUN_COPY.previewHeading} description={RUN_COPY.previewHint}>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex flex-col gap-4">
            <JudgePicker projectId={projectId} id="judge" picked={pickedJudge} onPick={setPickedJudge} />
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
                  {estimate.data.judge_model ? (
                    <p className="text-text-muted text-xs">
                      {RUN_COPY.judgeModel(estimate.data.judge_model)}
                    </p>
                  ) : null}
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
