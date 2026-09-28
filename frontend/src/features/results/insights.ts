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
