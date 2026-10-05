/**
 * How answers will be scored: the evaluators chosen from the task type, with each judge's
 * criteria editable. Saving creates a new evaluator-set version; the old one is kept.
 */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { EvaluatorSetVersionOut } from "@/lib/api/types"

import { TESTS_COPY } from "../copy"
import { useEditEvaluators } from "../hooks"

type Config = Record<string, unknown>

function ConstraintList({ list }: { list: unknown }) {
  const items = Array.isArray(list) ? list.map(String) : []
  if (items.length === 0) return <p className="text-text-secondary text-xs">{TESTS_COPY.noConstraints}</p>
  return (
    <ul className="text-text-secondary list-disc pl-5 text-xs">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

export function EvaluatorCard({
  projectId,
  versionId,
  set,
  frozen,
}: {
  projectId: string
  versionId: string
  set: EvaluatorSetVersionOut
  frozen: boolean
}) {
  const edit = useEditEvaluators(projectId, versionId)
  const [edits, setCriteria] = useState<Record<number, string>>({})
  const criteria: Record<number, string> = Object.fromEntries(
    set.evaluators
      .filter((e) => typeof (e.config as Config).criteria === "string")
      .map((e) => [e.position, edits[e.position] ?? String((e.config as Config).criteria)]),
  )
  const changed = set.evaluators.some(
    (e) => e.position in criteria && criteria[e.position] !== (e.config as Config).criteria,
  )

  async function save() {
    await edit.mutateAsync(
      set.evaluators.map((e) => ({
        evaluator_name: e.evaluator_name,
        evaluator_version: e.evaluator_version,
        config:
          e.position in criteria ? { ...(e.config as Config), criteria: criteria[e.position] } : e.config,
        threshold: e.threshold,
        weight: e.weight,
        required: e.required,
      })),
    )
    toast.success(TESTS_COPY.evaluatorsSaved)
  }

  return (
    <Section
      number={frozen ? 3 : 4}
      title={TESTS_COPY.evaluatorsHeading}
      description={TESTS_COPY.evaluatorsHint}
    >
      <div className="grid gap-3 md:grid-cols-2">
        {set.evaluators.map((e) => (
          <div key={e.id} className="bg-subtle ring-border flex flex-col gap-1.5 rounded-lg p-3 ring-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium capitalize">{e.evaluator_name.replaceAll("_", " ")}</span>
              <StatusBadge tone={(e.config as Config).kind === "deepeval" ? "violet" : "neutral"}>
                {(e.config as Config).kind === "deepeval" ? TESTS_COPY.judgeKind : TESTS_COPY.ruleKind}
              </StatusBadge>
              {e.required ? <StatusBadge tone="brand">{TESTS_COPY.requiredKind}</StatusBadge> : null}
            </div>
            <p className="text-text-secondary text-xs leading-relaxed">
              {(e.config as Config).kind === "deepeval"
                ? TESTS_COPY.judgeInfo
                : (TESTS_COPY.ruleInfo[e.evaluator_name] ?? "")}
            </p>
            {e.evaluator_name === "constraints" ? (
              <ConstraintList list={(e.config as Config).constraints} />
            ) : null}
            {Array.isArray((e.config as Config).evaluation_steps) ? (
              <div className="text-text-secondary text-xs">
                <p>{TESTS_COPY.stepsInfo}</p>
                <ol className="list-decimal pl-5">
                  {((e.config as Config).evaluation_steps as unknown[]).map((step) => (
                    <li key={String(step)}>{String(step)}</li>
                  ))}
                </ol>
              </div>
            ) : null}
            {e.position in criteria ? (
              <>
                <Label htmlFor={`criteria-${e.position}`} className="text-muted-foreground text-xs">
                  {TESTS_COPY.criteria}
                </Label>
                {criteria[e.position].trim() === "" && !frozen ? (
                  <p className="text-warning-strong text-xs">{TESTS_COPY.noCriteria}</p>
                ) : null}
                {criteria[e.position] === "{rubric}" ? (
                  <p className="text-text-secondary text-xs">{TESTS_COPY.perCase}</p>
                ) : null}
                <Textarea
                  id={`criteria-${e.position}`}
                  placeholder={TESTS_COPY.criteriaPlaceholder}
                  rows={2}
                  disabled={frozen}
                  value={criteria[e.position]}
                  onChange={(event) => setCriteria({ ...edits, [e.position]: event.target.value })}
                />
              </>
            ) : null}
          </div>
        ))}
      </div>
      <ErrorMessage error={edit.error} />
      {changed && !frozen ? (
        <Button className="self-start" variant="outline" onClick={() => void save().catch(() => undefined)}>
          {TESTS_COPY.saveEvaluators}
        </Button>
      ) : null}
    </Section>
  )
}
