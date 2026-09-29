/**
 * Pure logbook logic: the filter state and how it becomes a query, the chips that show active
 * filters, comparing a model's JSON answer with the golden JSON field by field, and the
 * plain-language findings shown on the Analysis tab. No React here.
 */
import type { AnalysisOut, GroupStats } from "@/lib/api/types"

export type AnswerFilters = {
  experiment_ids: string[]
  prompt_version_ids: string[]
  models: string[]
  providers: string[]
  statuses: string[]
  sources: string[]
  categories: string[]
  failed_checks: string[]
  passed: "" | "true" | "false"
  run_number: string
  q: string
  date_from: string
  date_to: string
}

export const EMPTY_FILTERS: AnswerFilters = {
  experiment_ids: [],
  prompt_version_ids: [],
  models: [],
  providers: [],
  statuses: [],
  sources: [],
  categories: [],
  failed_checks: [],
  passed: "",
  run_number: "",
  q: "",
  date_from: "",
  date_to: "",
}

export type CallFilters = {
  experiment_ids: string[]
  purposes: string[]
  statuses: string[]
  models: string[]
  providers: string[]
  q: string
  date_from: string
  date_to: string
}

export const EMPTY_CALL_FILTERS: CallFilters = {
  experiment_ids: [],
  purposes: [],
  statuses: [],
  models: [],
  providers: [],
  q: "",
  date_from: "",
  date_to: "",
}

/** Drops empty values so the query string only carries what the user chose. */
export function toParams<T extends Record<string, string | string[]>>(filters: T): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value) ? value.length : value !== "") out[key] = value
  }
  if (typeof out.run_number === "string") out.run_number = Number(out.run_number)
  for (const key of ["date_from", "date_to"]) {
    if (typeof out[key] === "string")
      out[key] = new Date(`${out[key]}T${key === "date_from" ? "00:00:00" : "23:59:59"}`).toISOString()
  }
  return out
}

export function activeCount(filters: object, empty: object): number {
  return Object.entries(filters).filter(
    ([key, value]) => JSON.stringify(value) !== JSON.stringify((empty as Record<string, unknown>)[key]),
  ).length
}

export type FieldComparison = { field: string; golden: string; answer: string; match: boolean | null }

function show(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 0)
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(sorted(a)) === JSON.stringify(sorted(b))
}

function sorted(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sorted)
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, sorted(v)]),
    )
  return value
}

export function parseJson(text: string | null | undefined): Record<string, unknown> | null {
  if (!text) return null
  const cleaned = text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/```$/, "")
  try {
    const value: unknown = JSON.parse(cleaned)
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

/** Top-level fields of the golden JSON against the model's JSON; null when either is not a JSON object. */
export function compareFields(golden: string | null, answer: string | null): FieldComparison[] | null {
  const expected = parseJson(golden)
  const got = parseJson(answer)
  if (!expected || !got) return null
  const fields = [...new Set([...Object.keys(expected), ...Object.keys(got)])]
  return fields.map((field) => ({
    field,
    golden: field in expected ? show(expected[field]) : "—",
    answer: field in got ? show(got[field]) : "—",
    match: field in expected ? field in got && same(expected[field], got[field]) : null,
  }))
}

export function prettyJson(text: string | null | undefined): string {
  const value = parseJson(text)
  return value ? JSON.stringify(value, null, 2) : (text ?? "")
}

export type Cell = { version: number; model: string; rate: number | null; answers: number }

/** Model × prompt version grid of pass rates, for the heat table. */
export function grid(groups: GroupStats[]): {
  versions: number[]
  models: string[]
  cells: Map<string, Cell>
} {
  const versions = [...new Set(groups.map((g) => g.prompt_version))].sort((a, b) => a - b)
  const models = [...new Set(groups.map((g) => g.model))].sort()
  const cells = new Map<string, Cell>()
  for (const g of groups)
    cells.set(`${g.model}|${g.prompt_version}`, {
      version: g.prompt_version,
      model: g.model,
      rate: g.pass_rate,
      answers: g.answers,
    })
  return { versions, models, cells }
}

const pct = (v: number) => `${Math.round(v * 100)}%`

/** Plain sentences about the filtered answers, most useful first. */
export function findings(analysis: AnalysisOut): string[] {
  const out: string[] = []
  const { totals, groups, failed_checks: checks } = analysis
  if (totals.answers === 0) return ["No answers match these filters."]
  const rated = groups.filter((g) => g.pass_rate !== null)
  const best = [...rated].sort((a, b) => (b.pass_rate ?? 0) - (a.pass_rate ?? 0))[0]
  if (best)
    out.push(
      `Highest pass rate: ${best.model} on v${best.prompt_version}, ${pct(best.pass_rate ?? 0)} of ${best.answers} answers.`,
    )
  const versions = [...new Set(rated.map((g) => g.prompt_version))].sort((a, b) => a - b)
  if (versions.length >= 2) {
    const mean = (v: number) => {
      const rows = rated.filter((g) => g.prompt_version === v)
      return rows.reduce((s, g) => s + (g.pass_rate ?? 0), 0) / rows.length
    }
    const first = versions[0]
    const last = versions[versions.length - 1]
    const change = Math.round((mean(last) - mean(first)) * 100)
    out.push(
      `Average pass rate across models went from ${pct(mean(first))} on v${first} to ${pct(mean(last))} on v${last} (${change >= 0 ? "+" : ""}${change} points).`,
    )
  }
  if (checks[0]) out.push(`Most common failed check: “${checks[0].check}”, ${checks[0].failures} failures.`)
  const priced = groups.filter((g) => g.cost !== null && g.answers > 0)
  if (priced.length >= 2) {
    const perAnswer = (g: GroupStats) => Number(g.cost) / g.answers
    const cheapest = [...priced].sort((a, b) => perAnswer(a) - perAnswer(b))[0]
    const dearest = [...priced].sort((a, b) => perAnswer(b) - perAnswer(a))[0]
    if (cheapest !== dearest && perAnswer(cheapest) > 0)
      out.push(
        `${cheapest.model} costs about ${(perAnswer(dearest) / perAnswer(cheapest)).toFixed(1)}× less per answer than ${dearest.model}.`,
      )
  }
  const broken = groups.filter((g) => g.failed_calls > 0)
  for (const g of broken)
    out.push(
      `${g.model} on v${g.prompt_version}: ${g.failed_calls} of ${g.answers} calls failed, so its pass rate is not meaningful.`,
    )
  if (totals.unknown_price_answers > 0)
    out.push(
      `${totals.unknown_price_answers} answers used a model with an unknown price, so cost is left blank.`,
    )
  return out
}
