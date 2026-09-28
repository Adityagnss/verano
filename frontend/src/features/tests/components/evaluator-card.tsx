/**
 * How answers will be scored: the evaluators chosen from the task type, with each judge's
 * criteria editable. Saving creates a new evaluator-set version; the old one is kept.
 */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { EvaluatorSetVersionOut } from "@/lib/api/types"

import { TESTS_COPY } from "../copy"
import { useEditEvaluators } from "../hooks"

type Config = Record<string, unknown>

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
    <Card size="sm">
      <CardHeader>
        <CardTitle>{TESTS_COPY.evaluatorsHeading}</CardTitle>
        <CardDescription>{TESTS_COPY.evaluatorsHint}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {set.evaluators.map((e) => (
          <div key={e.id} className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">{e.evaluator_name.replaceAll("_", " ")}</span>
            {e.position in criteria ? (
              <>
                <Label htmlFor={`criteria-${e.position}`} className="text-muted-foreground text-xs">
                  {TESTS_COPY.criteria}
                </Label>
                <Textarea
                  id={`criteria-${e.position}`}
                  rows={2}
                  disabled={frozen}
                  value={criteria[e.position]}
                  onChange={(event) => setCriteria({ ...edits, [e.position]: event.target.value })}
                />
              </>
            ) : null}
          </div>
        ))}
        <ErrorMessage error={edit.error} />
        {changed && !frozen ? (
          <Button className="self-start" variant="outline" onClick={() => void save().catch(() => undefined)}>
            {TESTS_COPY.saveEvaluators}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  )
}
