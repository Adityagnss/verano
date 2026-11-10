/**
 * Plain-language takeaways from the per-model metrics: which model is best on each
 * dimension (highest quality / pass rate / consistency, lowest time / cost per call), and
 * which models had calls fail, so the page says the answer before the table shows the numbers.
 */
import type { ModelMetricsOut } from "@/lib/api/types"

export type Column = "quality" | "pass_rate" | "consistency" | "latency_ms" | "cost_per_call"
const HIGHER_IS_BETTER: Record<Column, boolean> = {
  quality: true,
  pass_rate: true,
  consistency: true,
  latency_ms: false,
  cost_per_call: false,
}

function value(model: ModelMetricsOut, column: Column): number | null {
  const raw = model[column]
  return raw === null || raw === undefined ? null : Number(raw)
}

export function bestOn(models: ModelMetricsOut[], column: Column): ModelMetricsOut | null {
  const usable = models.filter((m) => value(m, column) !== null && m.failed_calls < m.cases)
  if (usable.length === 0) return null
  const sign = HIGHER_IS_BETTER[column] ? 1 : -1
  return usable.reduce((a, b) => (sign * (value(b, column)! - value(a, column)!) > 0 ? b : a))
}

/** Highlight only a real winner: at least two models that ran, and not a tie across all of them. */
export function isBest(models: ModelMetricsOut[], model: ModelMetricsOut, column: Column): boolean {
  const usable = models.filter((m) => value(m, column) !== null && m.failed_calls < m.cases)
  if (usable.length < 2) return false
  const values = new Set(usable.map((m) => value(m, column)))
  return values.size > 1 && bestOn(models, column)?.model_profile_id === model.model_profile_id
}

export function brokenModels(models: ModelMetricsOut[]): ModelMetricsOut[] {
  return models.filter((m) => m.failed_calls > 0)
}

export type Verdict =
  | { kind: "none" }
  | { kind: "unfair" }
  | { kind: "single" | "clear" | "close" | "unproven"; winner: ModelMetricsOut }

/** The winner on quality, and how sure we are, in terms the page can say in plain words. */
export function verdict(models: ModelMetricsOut[], ranked: boolean): Verdict {
  if (!ranked) return { kind: "unfair" }
  const winner = bestOn(models, "quality")
  if (!winner) return { kind: "none" }
  const others = models.filter(
    (m) => m.model_profile_id !== winner.model_profile_id && m.failed_calls < m.cases,
  )
  if (others.length === 0) return { kind: "single", winner }
  const labelled = others.filter((m) => m.vs_best)
  if (labelled.length === 0) return { kind: "unproven", winner }
  const clear = labelled.every((m) => m.vs_best?.label === "clear difference")
  return { kind: clear ? "clear" : "close", winner }
}

/** The model with the most quality for each dollar, or null when cost or quality is missing. */
export function bestValue(models: ModelMetricsOut[]): ModelMetricsOut | null {
  const usable = models.filter(
    (m) =>
      m.quality !== null &&
      m.cost_per_call !== null &&
      Number(m.cost_per_call) > 0 &&
      m.failed_calls < m.cases,
  )
  if (usable.length === 0) return null
  const score = (m: ModelMetricsOut) => Number(m.quality) / Number(m.cost_per_call)
  return usable.reduce((a, b) => (score(b) > score(a) ? b : a))
}
