/**
 * Pure calculations behind the dashboard: which experiments count, how models trend across
 * prompt versions, where the money went, and the plain-language findings. No React here.
 */
import type { CostSummary, ExperimentOut, ResultsOut } from "@/lib/api/types"

export type Finished = { experiment: ExperimentOut; results: ResultsOut; label: string }
export type Point = { index: number; label: string; date: string; value: number | null }
export type Trend = { model: string; points: Point[] }
export type SpendPart = { key: string; label: string; cost: number; calls: number }

const PURPOSE_LABELS: Record<string, string> = {
  test_run: "Running your test cases",
  generation: "Writing test cases",
  judge: "AI judges scoring answers",
  assistant: "Improving the prompt",
}

export function pct(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function versionLabels(versions: { id: string; version: number }[]): Map<string, string> {
  return new Map(versions.map((v) => [v.id, `v${v.version}`]))
}

/** Completed experiments that have scores, oldest first, at most `limit` of the newest. */
export function finishedExperiments(
  experiments: ExperimentOut[],
  results: Map<string, ResultsOut>,
  labels: Map<string, string>,
  limit = 10,
): Finished[] {
  return experiments
    .filter((e) => e.status === "completed" && (results.get(e.id)?.models.length ?? 0) > 0)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .slice(-limit)
    .map((experiment) => ({
      experiment,
      results: results.get(experiment.id)!,
      label: labels.get(experiment.prompt_version_id) ?? "v?",
    }))
}

/** One line per model: its pass rate in each finished experiment (null when it was not in it). */
export function trends(finished: Finished[]): Trend[] {
  const models = [...new Set(finished.flatMap((f) => f.results.models.map((m) => m.model)))].sort()
  return models.map((model) => ({
    model,
    points: finished.map((f, index) => ({
      index,
      label: f.label,
      date: f.experiment.created_at,
      value: f.results.models.find((m) => m.model === model)?.pass_rate ?? null,
    })),
  }))
}

export function spend(cost: CostSummary | undefined): SpendPart[] {
  return Object.entries(cost?.by_purpose ?? {})
    .map(([key, part]) => ({
      key,
      label: PURPOSE_LABELS[key] ?? key,
      cost: Number(part.cost),
      calls: part.calls,
    }))
    .filter((part) => part.calls > 0)
    .sort((a, b) => b.cost - a.cost)
}

export function usd(value: number): string {
  if (value === 0) return "$0.00"
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`
}

/** Plain sentences about the newest experiment and the trend, most useful first. */
export function insights(finished: Finished[], cost: CostSummary | undefined): string[] {
  const out: string[] = []
  const latest = finished.at(-1)
  if (latest) {
    const models = latest.results.models
    const best = [...models].sort((a, b) => b.pass_rate - a.pass_rate)[0]
    out.push(`${best.model} passed the most test cases in the latest experiment: ${pct(best.pass_rate)}.`)
    const priced = models.filter((m) => m.cost_per_call !== null && Number(m.cost_per_call) > 0)
    const close = priced
      .filter((m) => m.pass_rate >= best.pass_rate - 0.05)
      .sort((a, b) => Number(a.cost_per_call) - Number(b.cost_per_call))[0]
    if (
      close &&
      close.model !== best.model &&
      best.cost_per_call !== null &&
      Number(best.cost_per_call) > 0
    ) {
      const ratio = Number(best.cost_per_call) / Number(close.cost_per_call)
      if (ratio >= 1.5)
        out.push(
          `${close.model} is within 5 points of the best (${pct(close.pass_rate)}) and costs about ${ratio.toFixed(1)}× less per call.`,
        )
    }
    for (const m of models.filter((x) => x.failed_calls > 0))
      out.push(
        `${m.model}: ${m.failed_calls} of ${m.cases} calls failed, so its scores are not meaningful. Open its failed cases in Results.`,
      )
    const unsteady = models.filter((m) => m.consistency !== null && m.consistency < 0.8)
    for (const m of unsteady)
      out.push(`${m.model} is not consistent (${pct(m.consistency ?? 0)} same result across runs).`)
  }
  if (finished.length >= 2) {
    const bestOf = (f: Finished) => Math.max(...f.results.models.map((m) => m.pass_rate))
    const first = finished[0]
    const last = finished[finished.length - 1]
    const change = Math.round((bestOf(last) - bestOf(first)) * 100)
    out.push(
      change === 0
        ? `The best pass rate has not moved since ${first.label} (${pct(bestOf(first))}).`
        : `The best pass rate went from ${pct(bestOf(first))} (${first.label}) to ${pct(bestOf(last))} (${last.label}): ${change > 0 ? "+" : ""}${change} points.`,
    )
  }
  if ((cost?.calls_with_unknown_price ?? 0) > 0)
    out.push("Some calls used models whose price is unknown, so the total spent is a minimum.")
  return out
}
