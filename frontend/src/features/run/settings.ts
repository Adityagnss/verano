/**
 * The sampling settings of one model in the Run step: the starting values, turning what was
 * typed into the request, and what is wrong with it. Pure functions, no React.
 *
 * Values are only sent for settings the model's profile lists; a setting a model does not
 * support is never sent. Mirrors the backend rules (engine/sampling.py), which still decide.
 */
import type { ExperimentCreate, ModelProfileOut } from "@/lib/api/types"

export const MAX_RUNS = 5
export const MAX_SEED = 2 ** 31 - 1 - (MAX_RUNS - 1)
export const MAX_STOP = 4
export const MAX_STOP_CHARS = 100
export const BENCHMARK_SEED = "42"

export type Row = {
  include: boolean
  runs: string
  temperature: string
  max_tokens: string
  top_p: string
  top_k: string
  seed: string
  presence_penalty: string
  frequency_penalty: string
  stop: string
}

export type Field = Exclude<keyof Row, "include">
export type Problems = Partial<Record<Field, string>>

export const ADVANCED = ["seed", "top_p", "top_k", "frequency_penalty", "presence_penalty", "stop"] as const
const NUMERIC = [
  "temperature",
  "max_tokens",
  "top_p",
  "top_k",
  "seed",
  "presence_penalty",
  "frequency_penalty",
] as const
const WHOLE = new Set<Field>(["max_tokens", "top_k", "seed"])

export const supports = (m: ModelProfileOut, name: string) => name in (m.parameters ?? {})

function clamp(m: ModelProfileOut, name: string, value: number): string {
  const { min, max } = m.parameters?.[name] ?? {}
  return String(Math.min(max ?? value, Math.max(min ?? value, value)))
}

/** Benchmark defaults: temperature 0 and a fixed seed, where the model accepts them. */
export function defaultRow(m: ModelProfileOut): Row {
  return {
    include: true,
    runs: "1",
    temperature: supports(m, "temperature") ? clamp(m, "temperature", 0) : "",
    max_tokens: "",
    top_p: "",
    top_k: "",
    seed: supports(m, "seed") ? BENCHMARK_SEED : "",
    presence_penalty: "",
    frequency_penalty: "",
    stop: "",
  }
}

export type Randomness = "repeatable" | "default" | "custom"

/** Repeatable: temperature 0 and the benchmark seed where the model accepts them. Default: the provider decides. */
export function withRandomness(m: ModelProfileOut, row: Row, mode: Exclude<Randomness, "custom">): Row {
  const repeatable = mode === "repeatable"
  return {
    ...row,
    temperature: repeatable && supports(m, "temperature") ? clamp(m, "temperature", 0) : "",
    seed: repeatable && supports(m, "seed") ? BENCHMARK_SEED : "",
    top_p: "",
  }
}

/** Which choice the current rows match, or "custom" when they were edited by hand. */
export function randomnessOf(models: ModelProfileOut[], rows: Record<string, Row>): Randomness {
  for (const mode of ["repeatable", "default"] as const) {
    const same = models.every((m) => {
      const row = rows[m.id] ?? defaultRow(m)
      const expected = withRandomness(m, row, mode)
      return (
        row.temperature === expected.temperature && row.seed === expected.seed && row.top_p === expected.top_p
      )
    })
    if (same) return mode
  }
  return "custom"
}

/** One stop sequence per line; `\n`, `\t` and `\\` stand for a newline, a tab and a backslash. */
export function parseStop(text: string): string[] {
  return text
    .split("\n")
    .map((line) =>
      line
        .replace(/\r$/, "")
        .replace(/\\([nt\\])/g, (_, c: string) => (c === "n" ? "\n" : c === "t" ? "\t" : "\\")),
    )
    .filter((line) => line !== "")
}

export function problems(m: ModelProfileOut, row: Row): Problems {
  const found: Problems = {}
  if (!/^\d+$/.test(row.runs.trim()) || Number(row.runs) < 1 || Number(row.runs) > MAX_RUNS)
    found.runs = `Whole number from 1 to ${MAX_RUNS}.`
  for (const name of NUMERIC) {
    const text = row[name].trim()
    if (text === "" || !supports(m, name)) continue
    const value = Number(text)
    const { min, max } = m.parameters?.[name] ?? {}
    if (!Number.isFinite(value)) found[name] = "Enter a number."
    else if (WHOLE.has(name) && !Number.isInteger(value)) found[name] = "Whole number."
    else if (name === "seed" && (value < 0 || value > MAX_SEED)) found[name] = `From 0 to ${MAX_SEED}.`
    else if (name === "top_k" && value < 1) found[name] = "At least 1."
    else if (name === "max_tokens" && value < 1) found[name] = "At least 1."
    else if (min != null && value < min) found[name] = `At least ${min}.`
    else if (max != null && value > max) found[name] = `At most ${max}.`
  }
  if (supports(m, "stop")) {
    const stop = parseStop(row.stop)
    if (new Set(stop).size > MAX_STOP) found.stop = `At most ${MAX_STOP} sequences.`
    else if (stop.some((s) => s.length > MAX_STOP_CHARS))
      found.stop = `Each at most ${MAX_STOP_CHARS} characters.`
  }
  return found
}

/** A heads-up that is not an error: some Claude models refuse temperature and top_p together. */
export function warning(m: ModelProfileOut, row: Row): string | null {
  const both = row.temperature.trim() !== "" && row.top_p.trim() !== ""
  return m.provider === "anthropic" && both && supports(m, "top_p")
    ? "Some Claude models refuse temperature and top_p together. If calls fail, clear one."
    : null
}

/** How many advanced settings carry a value (for the collapsed summary). */
export function advancedCount(m: ModelProfileOut, row: Row): number {
  return ADVANCED.filter(
    (name) => supports(m, name) && (name === "stop" ? parseStop(row.stop).length : row[name].trim()),
  ).length
}

export function toParams(m: ModelProfileOut, row: Row): Record<string, number | string[]> {
  const params: Record<string, number | string[]> = {}
  for (const name of NUMERIC)
    if (supports(m, name) && row[name].trim() !== "") params[name] = Number(row[name])
  const stop = parseStop(row.stop)
  if (supports(m, "stop") && stop.length > 0) params.stop = stop
  return params
}

/** The request, or null when nothing is included or an included model has a wrong value. */
export function toBody(
  models: ModelProfileOut[],
  rows: Record<string, Row>,
  budget: string,
): ExperimentCreate | null {
  const chosen = models.filter((m) => (rows[m.id] ?? defaultRow(m)).include)
  if (chosen.length === 0) return null
  const budgetNumber = Number(budget)
  if (budget.trim() !== "" && !(Number.isFinite(budgetNumber) && budgetNumber > 0)) return null
  const entries = chosen.map((m) => ({ m, row: rows[m.id] ?? defaultRow(m) }))
  if (entries.some(({ m, row }) => Object.keys(problems(m, row)).length > 0)) return null
  return {
    models: entries.map(({ m, row }) => ({
      model_profile_id: m.id,
      runs: Number(row.runs),
      params: toParams(m, row),
    })),
    budget_cap: budget.trim() ? budget.trim() : null,
    split_scope: "all",
  }
}
