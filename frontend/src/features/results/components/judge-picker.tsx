/**
 * Choose the model that judges the answers: the suggested one is preselected, every model of the
 * project is possible, and picking one that is also being tested shows a warning (a model tends
 * to favour its own answers).
 */
"use client"

import { useState } from "react"

import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { useModels } from "@/features/keys/hooks"
import type { JudgeChoice } from "@/lib/api/types"

import { RESULTS_COPY } from "../copy"
import { useJudgeSuggestion } from "../hooks"

export const judgeKey = (j: JudgeChoice) => `${j.credential_id}|${j.model}`

/** The judge to use: the person's pick, else the suggestion. */
export function useChosenJudge(projectId: string, picked: string): JudgeChoice | null {
  const suggestion = useJudgeSuggestion(projectId)
  const candidates = suggestion.data?.candidates ?? []
  return candidates.find((c) => judgeKey(c) === picked) ?? suggestion.data?.suggested ?? null
}

export function JudgePicker({
  projectId,
  id,
  picked,
  onPick,
  label = RESULTS_COPY.judgeLabel,
  forJudging = true,
}: {
  projectId: string
  id: string
  picked: string
  onPick: (key: string) => void
  label?: string
  /** False when the model writes rather than judges: the self-judging warning and reason don't apply. */
  forJudging?: boolean
}) {
  const suggestion = useJudgeSuggestion(projectId)
  const models = useModels(projectId)
  const chosen = useChosenJudge(projectId, picked)
  const candidates = suggestion.data?.candidates ?? []
  const name = (c: JudgeChoice) =>
    models.data?.find((m) => m.credential_id === c.credential_id && m.model_name === c.model)?.display_name ??
    c.model
  const tested = new Set(
    (models.data ?? []).filter((m) => m.is_selected).map((m) => `${m.credential_id}|${m.model_name}`),
  )
  const self = chosen !== null && tested.has(judgeKey(chosen))
  const suggested = suggestion.data?.suggested
  const [changing, setChanging] = useState(false)
  // The suggested model is used without asking: the choice is shown as a line, and opens on "Change".
  const compact = chosen !== null && picked === "" && !changing
  return (
    <div className="flex max-w-md flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {compact ? (
        <p className="text-sm">
          <span className="font-medium">{name(chosen)}</span>{" "}
          <span className="text-text-muted">({RESULTS_COPY.judgeSuggested})</span>{" "}
          <button
            type="button"
            id={id}
            className="text-accent text-xs font-medium hover:underline"
            onClick={() => setChanging(true)}
          >
            {RESULTS_COPY.judgeChange}
          </button>
        </p>
      ) : (
        <NativeSelect id={id} value={chosen ? judgeKey(chosen) : ""} onChange={(e) => onPick(e.target.value)}>
          {chosen === null ? <option value="">{RESULTS_COPY.judgeNone}</option> : null}
          {candidates.map((c) => (
            <option key={judgeKey(c)} value={judgeKey(c)}>
              {name(c)}
              {suggested && judgeKey(suggested) === judgeKey(c) ? ` (${RESULTS_COPY.judgeSuggested})` : ""}
            </option>
          ))}
        </NativeSelect>
      )}
      {forJudging ? (
        <p className="text-text-muted text-xs">{suggestion.data?.reason ?? RESULTS_COPY.judgeHint}</p>
      ) : null}
      {forJudging && self ? <p className="text-warning-strong text-xs">{RESULTS_COPY.judgeSelf}</p> : null}
    </div>
  )
}
