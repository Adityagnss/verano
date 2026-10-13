/**
 * The Task Spec card: pick the model that writes the test cases, let it describe the task,
 * then confirm or edit the description. Nothing is generated from an unconfirmed task.
 */
"use client"

import { CircleCheck } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { GeneratorModel, TaskSpec, TaskSpecOut } from "@/lib/api/types"

import { TESTS_COPY } from "../copy"
import { useConfirmSpec } from "../hooks"

type Form = {
  task_type: string
  goal: string
  output_format: string
  allowed: string
  constraints: string
  risks: string
}

const lines = (text: string) =>
  text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)

function toForm(spec: TaskSpec): Form {
  return {
    task_type: spec.task_type,
    goal: spec.goal,
    output_format: spec.output_format,
    allowed: (spec.allowed_outputs ?? []).join(", "),
    constraints: (spec.constraints ?? []).join("\n"),
    risks: (spec.risk_areas ?? []).join("\n"),
  }
}

function toSpec(base: TaskSpec, form: Form): TaskSpec {
  const allowed = form.allowed
    .split(",")
    .map((l) => l.trim())
    .filter(Boolean)
  return {
    ...base,
    task_type: form.task_type as TaskSpec["task_type"],
    goal: form.goal,
    output_format: form.output_format as TaskSpec["output_format"],
    allowed_outputs: allowed.length ? allowed : null,
    constraints: lines(form.constraints),
    risk_areas: lines(form.risks),
  }
}

export function modelKey(model: GeneratorModel): string {
  return `${model.credential_id}|${model.model}`
}

type Props = {
  projectId: string
  spec: TaskSpecOut | null
  models: GeneratorModel[]
  chosen: string
  onChoose: (key: string) => void
  onConfirmed: () => void
  locked: boolean
}

function SpecForm({
  projectId,
  spec,
  locked,
  onConfirmed,
}: {
  projectId: string
  spec: TaskSpecOut
  locked: boolean
  onConfirmed: () => void
}) {
  const confirm = useConfirmSpec(projectId)
  const [form, setForm] = useState<Form>(() => toForm(spec.spec))
  const [editing, setEditing] = useState(spec.status === "draft")

  async function save() {
    await confirm.mutateAsync({ specId: spec.id, spec: toSpec(spec.spec, form) })
    toast.success(TESTS_COPY.confirmed)
    setEditing(false)
    onConfirmed()
  }
  const set = (field: keyof Form) => (event: { target: { value: string } }) =>
    setForm({ ...form, [field]: event.target.value })

  return (
    <div className="flex flex-col gap-4">
      {!editing ? (
        <div className="bg-subtle ring-border flex flex-wrap items-start gap-3 rounded-lg p-3 text-sm ring-1">
          <p className="min-w-0 flex-1">
            <span className="font-medium">
              {TESTS_COPY.taskTypes[form.task_type as keyof typeof TESTS_COPY.taskTypes] ?? form.task_type}
            </span>
            {" · "}
            {TESTS_COPY.outputFormats[form.output_format as keyof typeof TESTS_COPY.outputFormats] ??
              form.output_format}
            {form.goal ? ` · ${form.goal}` : ""}
            {lines(form.constraints).length
              ? ` · ${TESTS_COPY.rulesCount(lines(form.constraints).length)}`
              : ""}
          </p>
          {!locked ? (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              {TESTS_COPY.editSpec}
            </Button>
          ) : null}
        </div>
      ) : null}
      <fieldset disabled={!editing} className={editing ? "grid gap-4 md:grid-cols-2" : "hidden"}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="task_type">{TESTS_COPY.taskType}</Label>
          <NativeSelect id="task_type" value={form.task_type} onChange={set("task_type")}>
            {Object.entries(TESTS_COPY.taskTypes).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="output_format">{TESTS_COPY.outputFormat}</Label>
          <NativeSelect id="output_format" value={form.output_format} onChange={set("output_format")}>
            {Object.entries(TESTS_COPY.outputFormats).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="goal">{TESTS_COPY.goal}</Label>
          <Input id="goal" value={form.goal} onChange={set("goal")} />
        </div>
        {form.task_type === "classification" ? (
          <div className="flex flex-col gap-1.5 md:col-span-2">
            <Label htmlFor="allowed">{TESTS_COPY.allowedOutputs}</Label>
            <Input id="allowed" value={form.allowed} onChange={set("allowed")} />
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="constraints">{TESTS_COPY.constraints}</Label>
          <Textarea id="constraints" rows={3} value={form.constraints} onChange={set("constraints")} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="risks">{TESTS_COPY.riskAreas}</Label>
          <Textarea id="risks" rows={3} value={form.risks} onChange={set("risks")} />
        </div>
      </fieldset>
      <ErrorMessage error={confirm.error} />
      {editing ? (
        <Button
          className="self-start"
          onClick={() => void save().catch(() => undefined)}
          disabled={confirm.isPending}
        >
          {TESTS_COPY.confirm}
        </Button>
      ) : null}
    </div>
  )
}

export function TaskSpecCard({ projectId, spec, models, chosen, onChoose, onConfirmed, locked }: Props) {
  const status = spec?.status
  const [changingWriter, setChangingWriter] = useState(false)
  const chosenName = models.find((m) => modelKey(m) === chosen)?.model ?? chosen
  return (
    <Section
      number={1}
      title={TESTS_COPY.specHeading}
      description={TESTS_COPY.specHint}
      badge={
        status === "confirmed" ? (
          <StatusBadge tone="success" icon={<CircleCheck />}>
            {TESTS_COPY.specConfirmed}
          </StatusBadge>
        ) : status === "draft" ? (
          <StatusBadge tone="warning">{TESTS_COPY.specDraft}</StatusBadge>
        ) : null
      }
    >
      <div className="flex max-w-md flex-col gap-1.5">
        <Label htmlFor="generator">{TESTS_COPY.generator}</Label>
        {chosen && !changingWriter && !locked ? (
          <p className="text-sm">
            <span className="font-medium">{chosenName}</span>{" "}
            <button
              type="button"
              id="generator"
              className="text-accent text-xs font-medium hover:underline"
              onClick={() => setChangingWriter(true)}
            >
              {TESTS_COPY.changeWriter}
            </button>
          </p>
        ) : (
          <NativeSelect
            id="generator"
            value={chosen}
            onChange={(e) => onChoose(e.target.value)}
            disabled={locked}
          >
            {models.map((model) => (
              <option key={modelKey(model)} value={modelKey(model)}>
                {model.model}
              </option>
            ))}
          </NativeSelect>
        )}
        <p className="text-text-muted text-xs">{TESTS_COPY.generatorHint}</p>
      </div>
      {spec?.warnings.map((warning) => (
        <div
          key={warning}
          className="bg-warning-soft text-warning-strong ring-warning/25 rounded-lg p-3 text-sm ring-1"
        >
          <span className="font-medium">{TESTS_COPY.generatorWarning}: </span>
          {warning}
        </div>
      ))}
      {spec ? (
        <SpecForm
          key={`${spec.id}-${spec.status}`}
          projectId={projectId}
          spec={spec}
          locked={locked}
          onConfirmed={onConfirmed}
        />
      ) : (
        <p className="text-text-secondary text-sm">{TESTS_COPY.specEmpty}</p>
      )}
    </Section>
  )
}
