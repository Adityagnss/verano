/**
 * Pure calculations behind the dashboard: which experiments count, how models trend across
 * prompt versions, where the money went, and the plain-language findings. No React here.
 */
import { unfairReasons } from "@/lib/fairness"
import type { CostSummary, ExperimentOut, ResultsOut, VersionComparisonOut } from "@/lib/api/types"

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

export function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`
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

/** Only runs you started yourself: Improve's candidate tests run on part of the cases and are not prompt versions
 * you saved, so they stay out of the dashboard's headline, trend and findings. */
export function yourRuns(finished: Finished[]): Finished[] {
  return finished.filter((f) => f.experiment.origin === "manual")
}

function versionNumber(label: string): number {
  return Number(label.replace(/^v/, "")) || 0
}

/** The newest finished run of each prompt version, oldest version first. */
export function latestPerVersion(finished: Finished[]): Finished[] {
  const by = new Map<string, Finished>()
  for (const f of finished) by.set(f.label, f) // `finished` is oldest first, so the last one wins
  return [...by.values()].sort((a, b) => versionNumber(a.label) - versionNumber(b.label))
}

/** The best pass rate any model reached in a run (null when none could be judged). */
function bestRate(f: Finished): number | null {
  const rates = f.results.models.map((m) => m.pass_rate).filter((r): r is number => r !== null)
  return rates.length ? Math.max(...rates) : null
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
export function insights(
  finished: Finished[],
  cost: CostSummary | undefined,
  proof: VersionComparisonOut | null = null,
): string[] {
  const out: string[] = []
  const latest = finished.at(-1)
  if (latest) {
    const models = latest.results.models
    const unjudged = models.reduce((sum, m) => sum + m.unscored_cases, 0)
    if (unjudged > 0)
      out.push(
        `${unjudged} answers in the latest experiment could not be judged, so they are left out of the numbers. Open Results to see why and score them again.`,
      )
    const judged = models.filter((m): m is typeof m & { pass_rate: number } => m.pass_rate !== null)
    if (judged.length === 0) return out
    const unfair = unfairReasons(latest.experiment)
    if (unfair.length) out.push(`The models were not run alike, so they are not ranked. ${unfair.join(" ")}`)
    const best = [...judged].sort((a, b) => b.pass_rate - a.pass_rate)[0]
    if (!unfair.length)
      out.push(`${best.model} passed the most test cases in the latest experiment: ${pct(best.pass_rate)}.`)
    const priced = judged.filter((m) => m.cost_per_call !== null && Number(m.cost_per_call) > 0)
    const close = (unfair.length ? [] : priced)
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
  // A change between two versions is only called an improvement (or a drop) for a model when the same comparison
  // used on Prompt versions finds a clear difference for it; otherwise the numbers are shown as not proven.
  const versions = latestPerVersion(finished)
  if (versions.length >= 2 && proof && proof.models.length) {
    const [older, newer] = versions.slice(-2)
    const rate = (f: Finished, model: string) =>
      f.results.models.find((m) => m.model === model)?.pass_rate ?? null
    const clear = proof.models.filter((m) => m.comparison.label === "clear difference")
    for (const m of clear) {
      const was = rate(older, m.model)
      const now = rate(newer, m.model)
      if (was !== null && now !== null)
        out.push(
          `${m.model}: ${newer.label} is clearly ${m.comparison.first_better ? "better" : "worse"} than ${older.label} (pass rate ${pct(was)} to ${pct(now)}).`,
        )
    }
    const was = bestRate(older)
    const now = bestRate(newer)
    if (!clear.length && was !== null && now !== null) {
      const tooFew = proof.models.every((m) => m.comparison.label === "too few cases")
      out.push(
        `Best pass rate: ${pct(now)} on ${newer.label}, ${pct(was)} on ${older.label}. This is not a proven difference (${tooFew ? "too few test cases" : "no clear difference"}), so it is not counted as an improvement.`,
      )
    }
  }
  if ((cost?.calls_with_unknown_price ?? 0) > 0)
    out.push("Some calls used models whose price is unknown, so the total spent is a minimum.")
  return out
}
