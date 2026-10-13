/**
 * How the answers were judged, and a way to change it: the judge model, each judged check's
 * criteria or evaluation steps, and a "try it on one answer" preview (cost shown first, nothing
 * scored). Score again with the changes makes a new evaluator-set version and a new scoring pass;
 * the earlier pass stays readable, and passes made with different criteria or judges are never mixed.
 */
"use client"

import { useMemo, useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { CaseResultOut, EvaluatorConfigIn, EvaluatorSetVersionOut } from "@/lib/api/types"

import { RESULTS_COPY } from "../copy"
import { useEvaluatorVersion, useRescoreEstimate, useScoreAgain, useTryEstimate, useTryJudge } from "../hooks"
import { JudgeCallList } from "./judge-calls"
import { JudgePicker, useChosenJudge } from "./judge-picker"

type Config = Record<string, unknown>
type Draft = { criteria: string; steps: string }

const isJudged = (e: { config: unknown }) => (e.config as Config).kind === "deepeval"

function draftOf(set: EvaluatorSetVersionOut): Record<string, Draft> {
  return Object.fromEntries(
    set.evaluators.filter(isJudged).map((e) => {
      const config = e.config as Config
      const steps = Array.isArray(config.evaluation_steps) ? config.evaluation_steps.map(String) : []
      return [e.evaluator_name, { criteria: String(config.criteria ?? ""), steps: steps.join("\n") }]
    }),
  )
}

/** The full checks list with the drafts applied (the format the API takes). */
function withDrafts(set: EvaluatorSetVersionOut, drafts: Record<string, Draft>): EvaluatorConfigIn[] {
  return set.evaluators.map((e) => {
    const draft = drafts[e.evaluator_name]
    const config: Config = { ...(e.config as Config) }
    if (draft) {
      delete config.criteria
      delete config.evaluation_steps
      if (draft.criteria.trim()) config.criteria = draft.criteria.trim()
      const steps = draft.steps
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
      if (steps.length) config.evaluation_steps = steps
    }
    return {
      evaluator_name: e.evaluator_name,
      evaluator_version: e.evaluator_version,
      config,
      threshold: e.threshold,
      weight: e.weight,
      required: e.required,
    }
  })
}

export function JudgingPanel({
  projectId,
  experimentId,
  versionId,
  cases,
}: {
  projectId: string
  experimentId: string
  versionId: string
  cases: CaseResultOut[]
}) {
  const version = useEvaluatorVersion(projectId, versionId)
  if (!version.data) return <ErrorMessage error={version.error} />
  // Keyed by the version so a new scoring pass starts from its own checks.
  return (
    <PanelBody
      key={version.data.id}
      projectId={projectId}
      experimentId={experimentId}
      set={version.data}
      cases={cases}
    />
  )
}

function PanelBody({
  projectId,
  experimentId,
  set,
  cases,
}: {
  projectId: string
  experimentId: string
  set: EvaluatorSetVersionOut
  cases: CaseResultOut[]
}) {
  const original = useMemo(() => draftOf(set), [set])
  const [drafts, setDrafts] = useState(original)
  const [picked, setPicked] = useState("")
  const [tryName, setTryName] = useState("")
  const [answerId, setAnswerId] = useState("")
  const judged = set.evaluators.filter(isJudged)
  const names = Object.keys(original)
  const stored = set.judge ? `${set.judge.credential_id}|${set.judge.model}` : ""
  const chosen = useChosenJudge(projectId, picked || stored)
  const changedChecks = names.some(
    (n) =>
      drafts[n].criteria.trim() !== original[n].criteria.trim() ||
      drafts[n].steps.trim() !== original[n].steps.trim(),
  )
  const changedJudge =
    chosen !== null && set.judge !== null && `${chosen.credential_id}|${chosen.model}` !== stored
  const checks = withDrafts(set, drafts)
  const quote = useRescoreEstimate(
    projectId,
    experimentId,
    changedJudge ? chosen : null,
    changedChecks ? checks : null,
  )
  const again = useScoreAgain(projectId)
  const answers = cases.flatMap((c) =>
    c.outputs
      .filter((o) => o.output !== null)
      .map((o) => ({
        id: o.test_case_run_id,
        label: `${Object.values(c.inputs).map(String).join(" ").slice(0, 60)} — ${o.model} #${o.run_number}`,
      })),
  )
  const target = tryName || names[0] || ""
  const tryAnswer = answerId || answers[0]?.id || ""
  const evaluator = checks.find((e) => e.evaluator_name === target)
  const tryBody =
    evaluator && tryAnswer
      ? { test_case_run_id: tryAnswer, evaluator, judge: changedJudge ? chosen : null }
      : null
  const tryQuote = useTryEstimate(projectId, experimentId, tryBody)
  const tryIt = useTryJudge(projectId, experimentId)
  if (judged.length === 0) return null

  return (
    <Section title={RESULTS_COPY.judgingHeading} description={RESULTS_COPY.judgingHint}>
      <details className="group">
        <summary className="text-accent cursor-pointer text-sm">{RESULTS_COPY.judgingOpen}</summary>
        <div className="mt-3 flex flex-col gap-4">
          <JudgePicker projectId={projectId} id="panel-judge" picked={picked || stored} onPick={setPicked} />
          {judged.map((e) => {
            const draft = drafts[e.evaluator_name]
            const update = (patch: Partial<Draft>) =>
              setDrafts({ ...drafts, [e.evaluator_name]: { ...draft, ...patch } })
            return (
              <div key={e.id} className="bg-subtle ring-border flex flex-col gap-1.5 rounded-lg p-3 ring-1">
                <span className="text-sm font-medium capitalize">
                  {e.evaluator_name.replaceAll("_", " ")}
                </span>
                <Label htmlFor={`criteria-${e.id}`} className="text-xs">
                  {RESULTS_COPY.criteria}
                </Label>
                <Textarea
                  id={`criteria-${e.id}`}
                  rows={2}
                  value={draft.criteria}
                  onChange={(event) => update({ criteria: event.target.value })}
                />
                <p className="text-text-muted text-xs">{RESULTS_COPY.criteriaHint}</p>
                <Label htmlFor={`steps-${e.id}`} className="text-xs">
                  {RESULTS_COPY.steps}
                </Label>
                <Textarea
                  id={`steps-${e.id}`}
                  rows={3}
                  value={draft.steps}
                  onChange={(event) => update({ steps: event.target.value })}
                />
                <p className="text-text-muted text-xs">{RESULTS_COPY.stepsHint}</p>
              </div>
            )
          })}
          {answers.length ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">{RESULTS_COPY.tryHeading}</h3>
              <div className="grid gap-3 md:grid-cols-2">
                {names.length > 1 ? (
                  <NativeSelect
                    aria-label="Check"
                    value={target}
                    onChange={(e) => setTryName(e.target.value)}
                  >
                    {names.map((n) => (
                      <option key={n} value={n}>
                        {n.replaceAll("_", " ")}
                      </option>
                    ))}
                  </NativeSelect>
                ) : null}
                <NativeSelect
                  aria-label={RESULTS_COPY.tryPick}
                  value={tryAnswer}
                  onChange={(e) => setAnswerId(e.target.value)}
                >
                  {answers.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <p className="text-text-muted text-xs">
                {tryQuote.data
                  ? RESULTS_COPY.tryCost(tryQuote.data.judge_calls, tryQuote.data.judge_cost ?? null)
                  : null}
              </p>
              <ErrorMessage error={tryQuote.error ?? tryIt.error} />
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                disabled={!tryBody || !tryQuote.data || tryIt.isPending}
                onClick={() => tryBody && tryIt.mutate(tryBody)}
              >
                {tryIt.isPending ? RESULTS_COPY.trying : RESULTS_COPY.tryRun}
              </Button>
              {tryIt.data ? (
                <div className="flex flex-col gap-2">
                  <p className="text-sm">
                    {tryIt.data.score.status === "unscored"
                      ? tryIt.data.score.reason
                      : `${RESULTS_COPY.tryResult(tryIt.data.score.value, tryIt.data.score.passed)} — ${tryIt.data.score.reason}`}
                  </p>
                  <JudgeCallList calls={tryIt.data.calls} />
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="flex flex-col gap-2">
            {changedChecks || changedJudge ? (
              <p className="text-text-secondary text-xs">
                {RESULTS_COPY.scoreAgainCost(quote.data?.judge_calls ?? null, quote.data?.judge_cost ?? null)}
              </p>
            ) : (
              <p className="text-text-muted text-xs">{RESULTS_COPY.nothingChanged}</p>
            )}
            <ErrorMessage error={quote.error ?? again.error} />
            <Button
              className="self-start"
              disabled={!(changedChecks || changedJudge) || again.isPending}
              onClick={() =>
                again.mutate({
                  experimentId,
                  judge: changedJudge ? chosen : null,
                  evaluators: changedChecks ? checks : null,
                })
              }
            >
              {again.isPending ? RESULTS_COPY.scoring : RESULTS_COPY.scoreWithChanges}
            </Button>
          </div>
        </div>
      </details>
    </Section>
  )
}
