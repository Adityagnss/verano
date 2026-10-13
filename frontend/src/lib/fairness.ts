/**
 * Whether the models in one experiment can be ranked against each other. Models that ran a different number of
 * times, or with different settings (for example one at temperature 0 and another at its own default), did not take
 * the same test, so a ranking between them says little. No React here.
 */
import type { ExperimentOut } from "@/lib/api/types"

type ModelConfig = { display_name?: string; runs?: number; params?: Record<string, unknown> }

function modelsOf(experiment: Pick<ExperimentOut, "config">): ModelConfig[] {
  const models = (experiment.config as { models?: ModelConfig[] } | undefined)?.models
  return Array.isArray(models) ? models : []
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

function describeParams(params: Record<string, unknown> | undefined): string {
  const entries = Object.entries(params ?? {})
  return entries.length
    ? entries.map(([key, value]) => `${key} ${String(value)}`).join(", ")
    : "its own defaults"
}

/** Plain reasons the models were not run alike; empty when they were (or when only one model ran). */
export function unfairReasons(experiment: Pick<ExperimentOut, "config">): string[] {
  const models = modelsOf(experiment)
  if (models.length < 2) return []
  const name = (m: ModelConfig) => m.display_name ?? "a model"
  const reasons: string[] = []
  if (new Set(models.map((m) => m.runs ?? 1)).size > 1)
    reasons.push(
      `The models answered each case a different number of times (${models.map((m) => `${name(m)}: ${m.runs ?? 1}`).join(", ")}).`,
    )
  if (models.some((m) => !same(m.params ?? {}, models[0].params ?? {})))
    reasons.push(
      `The models ran with different settings (${models.map((m) => `${name(m)}: ${describeParams(m.params)}`).join("; ")}).`,
    )
  return reasons
}
