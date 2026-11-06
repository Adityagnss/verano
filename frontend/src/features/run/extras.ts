/**
 * The Run step's extra choices (ADR 0039): named parameter sets applied to every model, the response format, and the
 * evaluator-set version picked by "update checks". Pure functions, no React. The backend still decides what a model accepts.
 */
import type { ExperimentCreate } from "@/lib/api/types"

export const COPY = {
  heading: "Compare settings, and ask for a format",
  setsHint:
    "Add named groups of settings (for example Strict and Creative). Every chosen model runs once per group, as its own column in the results. With no group, each model uses the settings above.",
  addSet: "Add a settings group",
  remove: "Remove",
  name: "Name",
  temperature: "Temperature",
  maxTokens: "Max tokens",
  topP: "Top p",
  effort: "Reasoning effort",
  effortDefault: "Not set",
  effortHint:
    "Only for models that think before they answer. Other models are refused with a message that says so.",
  formatLabel: "Answer format",
  formats: {
    text: "Free text",
    json_object: "JSON object",
    json_schema: "JSON that fits the task's output schema",
  },
  formatHint: "The format is sent with every call, and the checks still read each answer afterwards.",
  formatUnsupported: "Some chosen models can't do this",
  needsName: "Give every group a name.",
  sameName: "Each group needs its own name.",
  badNumber: "Use plain numbers (whole for max tokens).",
} as const

export type Format = "text" | "json_object" | "json_schema"

export type SetRow = {
  name: string
  temperature: string
  max_tokens: string
  top_p: string
  reasoning_effort: string
}

export type RunExtras = { sets: SetRow[]; format: Format; evaluatorVersionId: string | null }

export const NO_EXTRAS: RunExtras = { sets: [], format: "text", evaluatorVersionId: null }

export const newSet = (index: number): SetRow => ({
  name: `Group ${index + 1}`,
  temperature: "",
  max_tokens: "",
  top_p: "",
  reasoning_effort: "",
})

const number = (text: string) => text.trim() !== "" && Number.isFinite(Number(text))

/** What is wrong with the groups, in plain words; empty when they can be sent. */
export function setProblems(sets: SetRow[]): string[] {
  const found: string[] = []
  const names = sets.map((s) => s.name.trim().toLowerCase())
  if (names.some((n) => n === "")) found.push(COPY.needsName)
  if (new Set(names).size !== names.length) found.push(COPY.sameName)
  const bad = sets.some(
    (s) =>
      (s.temperature.trim() !== "" && !number(s.temperature)) ||
      (s.top_p.trim() !== "" && !number(s.top_p)) ||
      (s.max_tokens.trim() !== "" && !(number(s.max_tokens) && Number.isInteger(Number(s.max_tokens)))),
  )
  if (bad) found.push(COPY.badNumber)
  return found
}

/** The fields to add to the experiment request, or null while the groups are not valid. */
export function extrasBody(
  extras: RunExtras,
): Pick<ExperimentCreate, "param_sets" | "response_format" | "evaluator_set_version_id"> | null {
  if (setProblems(extras.sets).length > 0) return null
  return {
    param_sets: extras.sets.map((s) => {
      const params: Record<string, number | string> = {}
      if (s.temperature.trim() !== "") params.temperature = Number(s.temperature)
      if (s.top_p.trim() !== "") params.top_p = Number(s.top_p)
      if (s.max_tokens.trim() !== "") params.max_tokens = Number(s.max_tokens)
      if (s.reasoning_effort) params.reasoning_effort = s.reasoning_effort
      return { name: s.name.trim(), params }
    }),
    response_format: extras.format,
    ...(extras.evaluatorVersionId ? { evaluator_set_version_id: extras.evaluatorVersionId } : {}),
  }
}
