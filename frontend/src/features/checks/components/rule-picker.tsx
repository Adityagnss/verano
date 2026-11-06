/** The rule picker: the rule checks, what each does, its settings, and adding one with a pass mark. */
"use client"

import { useMemo, useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import type { EvaluatorSetVersionOut, RuleInfoOut } from "@/lib/api/types"

import { CHECKS_COPY } from "../copy"
import { buildRuleConfig, defaultThreshold, hasCheck, parseSettings, type RuleValues } from "../domain"
import { useRuleChecks } from "../hooks"
import type { AddCheck } from "./check-library"

const COPY = CHECKS_COPY.rules

function RuleForm({
  rule,
  taken,
  frozen,
  busy,
  add,
}: {
  rule: RuleInfoOut
  taken: boolean
  frozen: boolean
  busy: boolean
  add: AddCheck
}) {
  const fields = useMemo(() => parseSettings(rule.settings), [rule.settings])
  const [values, setValues] = useState<RuleValues>({})
  const [mark, setMark] = useState(String(Math.round(defaultThreshold(rule.name) * 100)))
  const [errors, setErrors] = useState<string[]>([])
  const set = (name: string, value: string | boolean) => setValues({ ...values, [name]: value })
  const markNumber = Number(mark)
  const markBad = !Number.isFinite(markNumber) || markNumber < 0 || markNumber > 100 || mark.trim() === ""

  function submit() {
    const built = buildRuleConfig(fields, values)
    const problems = markBad ? [...built.errors, "The pass mark must be between 0 and 100."] : built.errors
    setErrors(problems)
    if (problems.length) return
    void add(
      {
        evaluator_name: rule.name,
        evaluator_version: "1",
        config: built.config,
        threshold: markNumber / 100,
        weight: 1,
        required: false,
      },
      rule.title,
    )
  }

  return (
    <div className="bg-subtle ring-border flex flex-col gap-3 rounded-lg p-4 ring-1">
      <div>
        <h4 className="text-sm font-semibold">{rule.title}</h4>
        <p className="text-sm">{rule.description}</p>
      </div>
      {fields.length === 0 ? <p className="text-text-secondary text-xs">{COPY.noSettings}</p> : null}
      <div className="grid gap-3 md:grid-cols-2">
        {fields.map((field) => {
          const id = `rule-${rule.name}-${field.name}`
          const text = field.name.replaceAll("_", " ")
          if (field.kind === "bool")
            return (
              <label key={field.name} className="flex items-center gap-2 text-sm" htmlFor={id}>
                <Checkbox
                  id={id}
                  checked={values[field.name] === true}
                  onCheckedChange={(c) => set(field.name, c)}
                />
                {text}
                {field.hint ? <span className="text-text-muted text-xs">({field.hint})</span> : null}
              </label>
            )
          const multi = field.kind === "lines" || field.kind === "json"
          return (
            <div key={field.name} className="flex flex-col gap-1.5">
              <Label htmlFor={id}>
                {text}
                {field.required ? "" : ` (${COPY.optional})`}
              </Label>
              {multi ? (
                <Textarea
                  id={id}
                  rows={3}
                  className={field.kind === "json" ? "font-mono" : undefined}
                  value={String(values[field.name] ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                />
              ) : (
                <Input
                  id={id}
                  type="text"
                  inputMode={field.kind === "number" ? "decimal" : undefined}
                  value={String(values[field.name] ?? "")}
                  onChange={(e) => set(field.name, e.target.value)}
                />
              )}
              <p className="text-text-muted text-xs">
                {field.kind === "lines" ? COPY.lines : field.kind === "json" ? "JSON" : field.hint}
              </p>
            </div>
          )
        })}
        <div className="flex max-w-40 flex-col gap-1.5">
          <Label htmlFor={`rule-${rule.name}-mark`}>{COPY.passMark} (%)</Label>
          <Input
            id={`rule-${rule.name}-mark`}
            type="number"
            min={0}
            max={100}
            value={mark}
            aria-invalid={markBad ? true : undefined}
            onChange={(e) => setMark(e.target.value)}
          />
        </div>
      </div>
      <p className="text-text-muted text-xs">{COPY.passMarkHint}</p>
      {errors.length ? (
        <ul className="text-danger-strong list-disc pl-5 text-sm" role="alert">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
      {taken ? (
        <StatusBadge tone="info" className="self-start">
          {CHECKS_COPY.already}
        </StatusBadge>
      ) : (
        <Button className="self-start" variant="outline" disabled={frozen || busy} onClick={submit}>
          {busy ? CHECKS_COPY.adding : CHECKS_COPY.add}
        </Button>
      )}
    </div>
  )
}

export function RulePicker({
  projectId,
  set,
  frozen,
  busy,
  add,
}: {
  projectId: string
  set: EvaluatorSetVersionOut
  frozen: boolean
  busy: boolean
  add: AddCheck
}) {
  const rules = useRuleChecks(projectId)
  const [query, setQuery] = useState("")
  const [picked, setPicked] = useState<string | null>(null)
  if (rules.isPending) return <Skeleton className="h-40" aria-label={CHECKS_COPY.loading} />
  if (rules.error) return <ErrorMessage error={rules.error} />
  if (rules.data.length === 0) return <p className="text-text-muted text-sm">{COPY.unavailable}</p>
  const q = query.trim().toLowerCase()
  const shown = rules.data.filter(
    (r) => !q || `${r.title} ${r.name} ${r.description}`.toLowerCase().includes(q),
  )
  const chosen = rules.data.find((r) => r.name === picked) ?? null
  return (
    <div className="flex flex-col gap-3">
      <p className="text-text-secondary text-sm">{COPY.intro}</p>
      <div className="flex max-w-sm flex-col gap-1.5">
        <Label htmlFor="rule-search">{COPY.search}</Label>
        <Input
          id="rule-search"
          type="search"
          placeholder={COPY.searchPlaceholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <ul
          className="border-border flex max-h-96 flex-col overflow-y-auto rounded-lg border"
          aria-label={COPY.pick}
        >
          {shown.length === 0 ? <li className="text-text-muted p-3 text-sm">{COPY.empty}</li> : null}
          {shown.map((rule) => (
            <li key={rule.name} className="border-border border-b last:border-b-0">
              <button
                type="button"
                aria-pressed={picked === rule.name}
                onClick={() => setPicked(rule.name)}
                className="hover:bg-subtle aria-pressed:bg-subtle flex w-full flex-col gap-0.5 px-3 py-2 text-left"
              >
                <span className="flex items-center gap-2 text-sm font-medium">
                  {rule.title}
                  {hasCheck(set, rule.name) ? (
                    <StatusBadge tone="info">{CHECKS_COPY.already}</StatusBadge>
                  ) : null}
                </span>
                <span className="text-text-secondary text-xs">{rule.description}</span>
              </button>
            </li>
          ))}
        </ul>
        {chosen ? (
          <RuleForm
            key={chosen.name}
            rule={chosen}
            taken={hasCheck(set, chosen.name)}
            frozen={frozen}
            busy={busy}
            add={add}
          />
        ) : (
          <p className="text-text-muted text-sm">{COPY.pick}</p>
        )}
      </div>
    </div>
  )
}
