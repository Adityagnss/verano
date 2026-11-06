/** The Run step's parameter groups and answer format (ADR 0039). Self-contained: it holds no state of its own. */
"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"

import { useRunOptions } from "../extras-hooks"
import { COPY, newSet, setProblems, type Format, type RunExtras, type SetRow } from "../extras"

const FORMATS: Format[] = ["text", "json_object", "json_schema"]

export function RunExtrasPanel({
  projectId,
  chosen,
  value,
  onChange,
}: {
  projectId: string
  chosen: string[]
  value: RunExtras
  onChange: (next: RunExtras) => void
}) {
  const options = useRunOptions(projectId)
  const models = (options.data?.models ?? []).filter((m) => chosen.includes(m.model_profile_id))
  const max = options.data?.max_param_sets ?? 6
  const efforts = [...new Set(models.flatMap((m) => m.reasoning_efforts))]
  const unsupported = (format: Format) => models.some((m) => !m.response_formats.includes(format))
  const problems = setProblems(value.sets)

  function setField(index: number, field: keyof SetRow, text: string) {
    onChange({ ...value, sets: value.sets.map((s, i) => (i === index ? { ...s, [field]: text } : s)) })
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-sm font-medium">{COPY.heading}</legend>
      <p className="text-text-muted text-xs">{COPY.setsHint}</p>
      {value.sets.map((set, index) => (
        <div key={index} className="bg-subtle ring-border grid gap-2 rounded-lg p-3 ring-1 sm:grid-cols-5">
          <div className="flex flex-col gap-1">
            <Label htmlFor={`set-name-${index}`}>{COPY.name}</Label>
            <Input
              id={`set-name-${index}`}
              value={set.name}
              onChange={(e) => setField(index, "name", e.target.value)}
            />
          </div>
          {(
            [
              ["temperature", COPY.temperature],
              ["top_p", COPY.topP],
              ["max_tokens", COPY.maxTokens],
            ] as const
          ).map(([field, label]) => (
            <div key={field} className="flex flex-col gap-1">
              <Label htmlFor={`set-${field}-${index}`}>{label}</Label>
              <Input
                id={`set-${field}-${index}`}
                inputMode="decimal"
                value={set[field]}
                onChange={(e) => setField(index, field, e.target.value)}
              />
            </div>
          ))}
          <div className="flex flex-col gap-1">
            <Label htmlFor={`set-effort-${index}`}>{COPY.effort}</Label>
            <NativeSelect
              id={`set-effort-${index}`}
              value={set.reasoning_effort}
              disabled={efforts.length === 0}
              onChange={(e) => setField(index, "reasoning_effort", e.target.value)}
              className="h-9"
            >
              <option value="">{COPY.effortDefault}</option>
              {efforts.map((effort) => (
                <option key={effort} value={effort}>
                  {effort}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="sm:col-span-5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange({ ...value, sets: value.sets.filter((_, i) => i !== index) })}
            >
              {COPY.remove}
            </Button>
          </div>
        </div>
      ))}
      {efforts.length > 0 ? <p className="text-text-muted text-xs">{COPY.effortHint}</p> : null}
      {problems.map((problem) => (
        <p key={problem} role="alert" className="text-destructive text-xs">
          {problem}
        </p>
      ))}
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={value.sets.length >= max}
          onClick={() => onChange({ ...value, sets: [...value.sets, newSet(value.sets.length)] })}
        >
          {COPY.addSet}
        </Button>
      </div>
      <div className="flex max-w-md flex-col gap-1.5">
        <Label htmlFor="response-format">{COPY.formatLabel}</Label>
        <NativeSelect
          id="response-format"
          value={value.format}
          onChange={(e) => onChange({ ...value, format: e.target.value as Format })}
          className="h-9"
        >
          {FORMATS.map((format) => (
            <option key={format} value={format}>
              {COPY.formats[format]}
              {unsupported(format) ? ` (${COPY.formatUnsupported})` : ""}
            </option>
          ))}
        </NativeSelect>
        <p className="text-text-muted text-xs">{COPY.formatHint}</p>
      </div>
    </fieldset>
  )
}
