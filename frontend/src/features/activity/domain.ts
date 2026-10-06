/**
 * Activity numbers, worked out from the API's daily rows (pure, no I/O). The API sends one
 * row per day, project, key, model and purpose for the period shown and the one before it;
 * everything on the page (totals, changes, charts, rankings, trends) is summed from those.
 */
import type { ActivityOut, ActivityRow } from "@/lib/api/types"

export type Metric = "spend" | "requests" | "tokens"
export type Dimension = "model" | "provider" | "key" | "project" | "purpose"

export const METRICS: { value: Metric; label: string }[] = [
  { value: "spend", label: "Spend" },
  { value: "requests", label: "Requests" },
  { value: "tokens", label: "Tokens" },
]

export const DIMENSIONS: { value: Dimension; label: string }[] = [
  { value: "model", label: "Model" },
  { value: "provider", label: "Provider" },
  { value: "key", label: "API key" },
  { value: "project", label: "Project" },
  { value: "purpose", label: "Purpose" },
]

const PURPOSES: Record<string, string> = {
  test_run: "Test runs",
  judge: "Judge scoring",
  generation: "Test case writing",
  assistant: "Prompt assistant",
}

const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"]
export const OTHER_COLOR = "var(--series-other)"
export const TOP = 4

export function value(row: ActivityRow, metric: Metric): number {
  if (metric === "spend") return Number(row.cost)
  if (metric === "requests") return row.requests
  return row.input_tokens + row.output_tokens
}

export interface Totals {
  spend: number
  requests: number
  failed: number
  input: number
  output: number
  tokens: number
  cached: number
  reasoning: number
  inputWithCacheReport: number
  unknownPrice: number
}

export function totals(rows: ActivityRow[]): Totals {
  const sum = (pick: (row: ActivityRow) => number) => rows.reduce((total, row) => total + pick(row), 0)
  const input = sum((r) => r.input_tokens)
  const output = sum((r) => r.output_tokens)
  return {
    spend: sum((r) => Number(r.cost)),
    requests: sum((r) => r.requests),
    failed: sum((r) => r.failed),
    input,
    output,
    tokens: input + output,
    cached: sum((r) => r.cached_input_tokens),
    reasoning: sum((r) => r.reasoning_tokens),
    inputWithCacheReport: sum((r) => r.input_tokens_with_cache_report),
    unknownPrice: sum((r) => r.unknown_price_calls),
  }
}

/** Share of input tokens served from the provider's cache, among calls whose provider reports it. */
export function cacheHitRate(t: Totals): number | null {
  return t.inputWithCacheReport > 0 ? t.cached / t.inputWithCacheReport : null
}

/** What a million tokens cost on average, input and output together. */
export function blendedPerMillion(t: Totals): number | null {
  return t.tokens > 0 ? (t.spend / t.tokens) * 1_000_000 : null
}

export type Change = { kind: "none" } | { kind: "new" } | { kind: "gone" } | { kind: "pct"; value: number }

export function change(current: number, prior: number): Change {
  if (prior === 0 && current === 0) return { kind: "none" }
  if (prior === 0) return { kind: "new" }
  if (current === 0) return { kind: "gone" }
  return { kind: "pct", value: (current - prior) / prior }
}

export function split(data: ActivityOut | undefined, projectId: string | null) {
  const rows = (data?.rows ?? []).filter((row) => !projectId || row.project_id === projectId)
  return {
    current: rows.filter((row) => row.period === "current"),
    prior: rows.filter((row) => row.period === "prior"),
  }
}

/** Every day of the period, so days without calls still show as empty columns. */
export function daysOf(start: string, end: string): string[] {
  const days: string[] = []
  const cursor = new Date(`${start}T00:00:00Z`)
  const last = new Date(`${end}T00:00:00Z`)
  while (cursor <= last) {
    days.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return days
}

export function entityOf(row: ActivityRow, dimension: Dimension): string {
  if (dimension === "model") return row.model
  if (dimension === "provider") return row.provider
  if (dimension === "key") return row.key ?? `${row.provider}:no key`
  if (dimension === "project") return row.project_id
  return row.purpose
}

export function labeler(data: ActivityOut | undefined) {
  const projects = new Map((data?.projects ?? []).map((p) => [p.id, p.name]))
  const keys = new Map((data?.keys ?? []).map((k) => [k.id, k]))
  return (dimension: Dimension, id: string): { name: string; detail?: string } => {
    if (dimension === "project") return { name: projects.get(id) ?? "A deleted project" }
    if (dimension === "purpose") return { name: PURPOSES[id] ?? id }
    if (dimension === "key") {
      const key = keys.get(id)
      if (!key) return { name: id.replace(":", " ") }
      const ending = key.last4 ? `ending ${key.last4}` : "no key needed"
      const used = key.projects === 1 ? "1 project" : `${key.projects} projects`
      return {
        name: `${key.provider} ${ending}`,
        detail: [key.labels.join(", "), used].filter(Boolean).join(", "),
      }
    }
    return { name: id }
  }
}

export interface Ranked {
  id: string
  value: number
  share: number
}

export function ranking(rows: ActivityRow[], dimension: Dimension, metric: Metric): Ranked[] {
  const by = new Map<string, number>()
  for (const row of rows)
    by.set(entityOf(row, dimension), (by.get(entityOf(row, dimension)) ?? 0) + value(row, metric))
  const total = [...by.values()].reduce((a, b) => a + b, 0)
  return [...by.entries()]
    .map(([id, v]) => ({ id, value: v, share: total > 0 ? v / total : 0 }))
    .sort((a, b) => b.value - a.value || a.id.localeCompare(b.id))
}

/**
 * Colors follow the entity, never its rank in the chart shown: they are handed out once per
 * dimension, by how many requests each entity had in both periods, so switching the metric or
 * the tab never repaints a model. The first four get the validated series colors; the rest grey.
 */
export function palette(all: ActivityRow[], dimension: Dimension): (id: string) => string {
  const order = ranking(all, dimension, "requests").map((r) => r.id)
  return (id) => {
    const index = order.indexOf(id)
    return index >= 0 && index < SLOTS.length ? SLOTS[index] : OTHER_COLOR
  }
}

export interface Series {
  id: string
  color: string
  total: number
}

export interface Stacked {
  series: Series[]
  days: string[]
  values: Record<string, number>[] // per day: series id → value
}

/** Per-day values of the top entities (by the metric over the period), the rest summed as "other". */
export function stacked(
  rows: ActivityRow[],
  days: string[],
  dimension: Dimension,
  metric: Metric,
  colorOf: (id: string) => string,
): Stacked {
  const ranked = ranking(rows, dimension, metric).filter((r) => r.value > 0)
  const shown = ranked.slice(0, TOP)
  const ids = new Set(shown.map((r) => r.id))
  const series: Series[] = shown.map((r) => ({ id: r.id, color: colorOf(r.id), total: r.value }))
  const rest = ranked.slice(TOP).reduce((a, r) => a + r.value, 0)
  if (rest > 0) series.push({ id: "other", color: OTHER_COLOR, total: rest })
  const index = new Map(days.map((day, i) => [day, i]))
  const values = days.map(() => ({}) as Record<string, number>)
  for (const row of rows) {
    const i = index.get(row.day)
    if (i === undefined) continue
    const id = ids.has(entityOf(row, dimension)) ? entityOf(row, dimension) : "other"
    values[i][id] = (values[i][id] ?? 0) + value(row, metric)
  }
  return { series, days, values }
}

/** Fixed parts that add up to a whole per day (token kinds, input caching). */
export function parts(
  rows: ActivityRow[],
  days: string[],
  pieces: { id: string; color: string; pick: (row: ActivityRow) => number }[],
): Stacked {
  const index = new Map(days.map((day, i) => [day, i]))
  const values = days.map(() => ({}) as Record<string, number>)
  const total: Record<string, number> = {}
  for (const row of rows) {
    const i = index.get(row.day)
    if (i === undefined) continue
    for (const piece of pieces) {
      const v = piece.pick(row)
      values[i][piece.id] = (values[i][piece.id] ?? 0) + v
      total[piece.id] = (total[piece.id] ?? 0) + v
    }
  }
  return { series: pieces.map((p) => ({ id: p.id, color: p.color, total: total[p.id] ?? 0 })), days, values }
}

export function daily(
  rows: ActivityRow[],
  days: string[],
  metric: Metric,
  keep?: (row: ActivityRow) => boolean,
) {
  const index = new Map(days.map((day, i) => [day, i]))
  const out = days.map(() => 0)
  for (const row of rows) {
    const i = index.get(row.day)
    if (i !== undefined && (!keep || keep(row))) out[i] += value(row, metric)
  }
  return out
}

export interface Trend {
  id: string
  current: number
  change: Change
  line: number[]
}

/** Entities whose use moved by at least a tenth against the period before, biggest movers first. */
export function trending(
  current: ActivityRow[],
  prior: ActivityRow[],
  days: string[],
  dimension: Dimension,
  metric: Metric,
): Trend[] {
  const now = new Map(ranking(current, dimension, metric).map((r) => [r.id, r.value]))
  const before = new Map(ranking(prior, dimension, metric).map((r) => [r.id, r.value]))
  const ids = new Set([...now.keys(), ...before.keys()])
  const weight = (t: Trend) =>
    t.change.kind === "pct" ? Math.abs(t.change.value) : t.change.kind === "none" ? 0 : 10
  return [...ids]
    .map((id) => ({
      id,
      current: now.get(id) ?? 0,
      change: change(now.get(id) ?? 0, before.get(id) ?? 0),
      line: daily(current, days, metric, (row) => entityOf(row, dimension) === id),
    }))
    .filter(
      (t) =>
        t.change.kind === "new" ||
        t.change.kind === "gone" ||
        (t.change.kind === "pct" && Math.abs(t.change.value) >= 0.1),
    )
    .sort((a, b) => weight(b) - weight(a) || b.current - a.current)
}

const ERRORS: Record<string, string> = {
  rate_limited: "Rate limited by the provider",
  provider_timeout: "The provider took too long",
  provider_unavailable: "The provider was unavailable",
  provider_auth_error: "The key was refused",
  model_not_found: "The model doesn't exist for this key",
  provider_bad_request: "The provider refused the request",
  content_policy_blocked: "Blocked by the provider's content policy",
  structured_output_error: "The answer wasn't the JSON asked for",
  invalid_parameter: "A setting the model doesn't accept",
  provider_error: "Another provider error",
}

export function errorLabel(kind: string): string {
  return ERRORS[kind] ?? kind.replaceAll("_", " ")
}
